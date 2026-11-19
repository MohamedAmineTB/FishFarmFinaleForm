"""Knowledge base (RAG): ingestion pipeline for kb/*.md and hybrid search.

Hybrid search = full-text search (PostgreSQL tsvector + GIN) + vector similarity, merged with
Reciprocal Rank Fusion (k = 50). With pgvector the whole search runs in SQL (`kb_hybrid_search`,
HNSW index); without it the vector half runs in Python over the (small) corpus.

Embeddings: a local multilingual sentence-transformers model when installed
(EMBEDDING_BACKEND=sentence_transformers), otherwise a deterministic hashing embedder
(word + character-trigram feature hashing, 384 dimensions) that needs no download.
"""

import hashlib
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import get_settings

DIM = 384
RRF_K = 50
STOP = set(
    """a an and are as at be by can do does for from has have how i in is it its my of on or our that the
this to was what when where which who why will with you your le la les des de du un une et est que qui pour dans
sur ce cette mon ma mes en au aux il elle ils pas plus""".split()
)


def words(s: str) -> list[str]:
    raw = re.findall(r"\w+", s.lower(), flags=re.UNICODE)
    return [w for w in raw if len(w) > 2 and w not in STOP]


def _hash_embed(t: str) -> list[float]:
    v = np.zeros(DIM, dtype=np.float32)
    for w in words(t):
        feats = [w] + [f"#{w[i : i + 3]}" for i in range(max(1, len(w) - 2))]
        for f in feats:
            h = int(hashlib.md5(f.encode()).hexdigest(), 16)
            v[h % DIM] += (1.0 if (h >> 8) & 1 else -1.0) * (2.0 if f == w else 0.5)
    n = float(np.linalg.norm(v)) or 1.0
    return (v / n).tolist()


@lru_cache
def _st_model():
    from sentence_transformers import SentenceTransformer  # optional dependency

    return SentenceTransformer(get_settings().embedding_model)


def backend() -> str:
    b = get_settings().embedding_backend
    if b == "hash":
        return "hash"
    try:
        _st_model()
        return "sentence_transformers"
    except Exception:
        if b == "sentence_transformers":
            raise
        return "hash"


def embed(texts: list[str]) -> list[list[float]]:
    if backend() == "sentence_transformers":
        return [list(map(float, e)) for e in _st_model().encode(texts, normalize_embeddings=True)]
    return [_hash_embed(t) for t in texts]


def or_query(q: str) -> str:
    """Full-text query matching ANY meaningful word (natural questions rarely contain every word of a chunk)."""
    ws = sorted({re.sub(r"[^\w]", "", w) for w in words(q)} - {""})
    return " | ".join(ws) if ws else "zzzz"


def has_pgvector(db: Session) -> bool:
    return bool(
        db.execute(
            text(
                "SELECT 1 FROM information_schema.columns WHERE table_name = 'kb_chunks' AND column_name = 'embedding' "
                "AND udt_name = 'vector'"
            )
        ).first()
    )


# ---------------- ingestion (a small data pipeline: parse -> chunk -> embed -> load) ----------------


def parse_doc(path: Path) -> tuple[dict, list[tuple[str, str]]]:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = raw
    if raw.startswith("---"):
        _, fm, body = raw.split("---", 2)
        for line in fm.strip().splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    chunks: list[tuple[str, str]] = []
    section, buf = meta.get("title", path.stem), []
    for line in body.strip().splitlines():
        if line.startswith("## "):
            if buf:
                chunks.append((section, "\n".join(buf).strip()))
            section, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if buf:
        chunks.append((section, "\n".join(buf).strip()))
    # keep chunks between ~300 and ~800 tokens where possible: split very long sections on paragraphs
    out: list[tuple[str, str]] = []
    for sec, content in chunks:
        if len(content.split()) > 600:
            paras, cur = content.split("\n\n"), ""
            for p in paras:
                if len((cur + p).split()) > 450 and cur:
                    out.append((sec, cur.strip()))
                    cur = ""
                cur += p + "\n\n"
            if cur.strip():
                out.append((sec, cur.strip()))
        elif content:
            out.append((sec, content))
    return meta, out


def ingest(db: Session, kb_dir: Path | None = None) -> dict:
    kb_dir = kb_dir or Path(__file__).resolve().parents[3] / "kb"
    vec = has_pgvector(db)
    docs = chunks = 0
    for path in sorted(kb_dir.glob("*.md")):
        meta, parts = parse_doc(path)
        doc_id = meta.get("id", path.stem)
        db.execute(text("DELETE FROM kb_documents WHERE id = :id"), {"id": doc_id})
        db.execute(
            text(
                "INSERT INTO kb_documents (id, title, url, publisher, year, licence, species) "
                "VALUES (:id, :t, :u, :p, :y, :l, :s)"
            ),
            {
                "id": doc_id,
                "t": meta.get("title", path.stem),
                "u": meta.get("url", ""),
                "p": meta.get("publisher", ""),
                "y": int(meta["year"]) if meta.get("year") else None,
                "l": meta.get("licence"),
                "s": meta.get("species"),
            },
        )
        embs = embed([f"{s}\n{c}" for s, c in parts])
        for (sec, content), e in zip(parts, embs, strict=True):
            if vec:
                db.execute(
                    text("INSERT INTO kb_chunks (doc_id, section, content, embedding) VALUES (:d, :s, :c, CAST(:e AS vector))"),
                    {"d": doc_id, "s": sec, "c": content, "e": "[" + ",".join(f"{x:.6f}" for x in e) + "]"},
                )
            else:
                db.execute(
                    text("INSERT INTO kb_chunks (doc_id, section, content, embedding) VALUES (:d, :s, :c, :e)"),
                    {"d": doc_id, "s": sec, "c": content, "e": e},
                )
            chunks += 1
        docs += 1
    return {"documents": docs, "chunks": chunks, "embeddings": backend(), "pgvector": vec}


def ensure_ingested(db: Session) -> None:
    if not db.execute(text("SELECT 1 FROM kb_chunks LIMIT 1")).first():
        ingest(db)


# ---------------- search ----------------


def search(db: Session, query: str, species: str | None = None, k: int = 4) -> list[dict]:
    ensure_ingested(db)
    q_emb = embed([query])[0]
    tsq = or_query(query)
    if has_pgvector(db):
        rows = db.execute(
            text("SELECT chunk_id, score FROM kb_hybrid_search(:q, CAST(:e AS vector), :k, :sp)"),
            {"q": tsq, "e": "[" + ",".join(f"{x:.6f}" for x in q_emb) + "]", "k": k, "sp": species},
        ).all()
        ranked = [(int(cid), float(score)) for cid, score in rows]
    else:
        species_filter = "AND (CAST(:sp AS text) IS NULL OR d.species IS NULL OR d.species = CAST(:sp AS text))"
        fts = (
            db.execute(
                text(
                    "SELECT c.id FROM kb_chunks c JOIN kb_documents d ON d.id = c.doc_id "
                    f"WHERE c.tsv @@ to_tsquery('simple', :q) {species_filter} "
                    "ORDER BY ts_rank_cd(c.tsv, to_tsquery('simple', :q)) DESC LIMIT 50"
                ),
                {"q": tsq, "sp": species},
            )
            .scalars()
            .all()
        )
        allc = db.execute(
            text(f"SELECT c.id, c.embedding FROM kb_chunks c JOIN kb_documents d ON d.id = c.doc_id WHERE true {species_filter}"),
            {"sp": species},
        ).all()
        qv = np.array(q_emb)
        sims = sorted(((cid, float(np.dot(qv, np.array(e)))) for cid, e in allc if e), key=lambda x: -x[1])[:50]
        score: dict[int, float] = {}
        for r, cid in enumerate(fts, start=1):
            score[cid] = score.get(cid, 0) + 1.0 / (RRF_K + r)
        for r, (cid, _) in enumerate(sims, start=1):
            score[cid] = score.get(cid, 0) + 1.0 / (RRF_K + r)
        ranked = sorted(score.items(), key=lambda x: -x[1])[:k]
    if not ranked:
        return []
    ids = [cid for cid, _ in ranked]
    rows = {
        r.id: r
        for r in db.execute(
            text(
                "SELECT c.id, c.doc_id, c.section, c.content, d.title, d.url, d.publisher, d.year FROM kb_chunks c "
                "JOIN kb_documents d ON d.id = c.doc_id WHERE c.id = ANY(:ids)"
            ),
            {"ids": ids},
        ).all()
    }
    out = []
    for cid, sc in ranked:
        r = rows[cid]
        out.append(
            {
                "doc_id": r.doc_id,
                "title": r.title,
                "section": r.section,
                "url": r.url,
                "publisher": r.publisher,
                "year": r.year,
                "score": round(sc, 4),
                "text": r.content[:1200],
            }
        )
    return out


def source_label(hit: dict) -> str:
    """Short citation chip text, e.g. 'UF/IFAS Extension (EDIS FA002) · Dissolved oxygen for fish production'."""
    pub = hit["publisher"].split(" (")[0]
    return f"{pub} · {hit['title']}"
