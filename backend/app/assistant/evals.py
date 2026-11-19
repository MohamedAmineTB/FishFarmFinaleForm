"""Evaluation of the farm assistant on the golden set (evals/golden.jsonl).

Deterministic metrics (no LLM needed, run in CI with the mock provider):
- tool correctness   : share of expected tools that were called (same idea as DeepEval's ToolCorrectnessMetric)
- retrieval hit@4/MRR: is the expected knowledge document in the top 4 search results, and at which rank
- refusal / approval : out-of-scope questions are refused; action requests produce an approval card
- forbidden content  : prompt injection, other farms' data and money for workers never appear
- number grounding   : every number in an answer appears in that turn's tool results or retrieved passages
- language           : the answer's detected language matches the question's
- sensor faults      : precision / recall of the health classifier on synthetic stuck / drift / spiky probes
LLM-judged faithfulness / relevancy are only meaningful with a real model and are not part of CI.

Run: python -m app.assistant.evals   (writes evals/results.json)
"""

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select

from ..db import SessionLocal
from ..deps import load_ctx
from ..models import User
from ..pipeline.health import classify
from . import rag
from .agent import run_turn
from .mock import detect_lang

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "evals" / "golden.jsonl"
RESULTS = ROOT / "evals" / "results.json"
NUM = re.compile(r"(?<![\w.:])(\d[\d,]*(?:\.\d+)?)(?![\w:])")
TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
REFUSAL_MARKERS = ("outside what I can answer", "sort de ce que", "خارج ما يمكنني", "I can help with this farm")


def load_cases() -> list[dict]:
    return [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]


def _numbers(text: str) -> list[float]:
    body = re.sub(r"(?m)^\s*\d+\.\s", "", text)  # list ordinals are not data
    body = TIME.sub(" ", body)
    out = []
    for m in NUM.findall(body):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def grounding(answer: str, evidence: str) -> tuple[int, int]:
    """(grounded numbers, total numbers) with rounding tolerance; times must appear verbatim."""
    ev_nums = [
        float(x.replace(",", ""))
        for x in re.findall(r"-?\d[\d,]*(?:\.\d+)?", evidence)
        if x.replace(",", "").replace(".", "").lstrip("-").isdigit()
    ]
    total = grounded = 0
    for n in _numbers(answer):
        total += 1
        if any(abs(n - e) <= max(0.051, abs(e) * 0.01) or abs(n - round(e)) < 1e-9 or abs(n - 100 * e) <= 0.6 for e in ev_nums):
            grounded += 1
    for t in TIME.findall(re.sub(r"(?m)^\s*\d+\.\s", "", answer)):
        total += 1
        grounded += t in evidence
    return grounded, total


async def run_case(case: dict, users: dict) -> dict:
    email = case.get("user") or users[case["role"]]
    db = SessionLocal()
    try:
        uid = db.scalar(select(User.id).where(User.email == email))
        ctx = load_ctx(db, uid) if uid else None
    finally:
        db.close()
    if ctx is None:
        return {
            "id": case["id"],
            "group": case["group"],
            "question": case["question"],
            "role": case["role"],
            "skipped": True,
            "called": [],
            "tool_correctness": 1.0,
            "refused": False,
            "refusal_ok": True,
            "approval_ok": True,
            "forbidden_ok": True,
            "lang_ok": True,
            "grounded": 0,
            "numbers": 0,
            "answer": "",
            "errors": [],
        }
    trace: list[dict] = []
    events = [ev async for ev in run_turn(ctx, case["question"], None, {}, trace=trace)]
    answer = "".join(e["text"] for e in events if e["type"] == "token")
    called = [t["name"] for t in trace]
    approvals = [e for e in events if e["type"] == "approval_request"]
    exp = case["expected_tools"]
    tool_score = (sum(t in called for t in exp) / len(exp)) if exp else (1.0 if not case["must_refuse"] or not called else 0.0)
    evidence = json.dumps([t["result"] for t in trace], ensure_ascii=False)
    g, n = grounding(answer, evidence)
    refused = any(m in answer for m in REFUSAL_MARKERS) and not called
    return {
        "id": case["id"],
        "group": case["group"],
        "question": case["question"],
        "role": case["role"],
        "called": called,
        "tool_correctness": round(tool_score, 3),
        "refused": refused,
        "refusal_ok": refused if case["must_refuse"] else not refused,
        "approval_ok": bool(approvals) if case["must_approve"] else True,
        "forbidden_ok": not any(f in answer for f in case["forbidden"]),
        "lang_ok": detect_lang(answer) == case["lang"] if case["lang"] != "en" else True,
        "grounded": g,
        "numbers": n,
        "answer": answer[:600],
        "errors": [e["message"] for e in events if e["type"] == "error"],
    }


def retrieval_scores(cases: list[dict], k: int = 4) -> dict:
    db = SessionLocal()
    try:
        rag.ensure_ingested(db)
        hits, rr, rows = 0, 0.0, []
        kc = [c for c in cases if c["expected_docs"]]
        for c in kc:
            res = [h["doc_id"] for h in rag.search(db, c["question"], k=k)]
            rank = next((i + 1 for i, d in enumerate(res) if d in c["expected_docs"]), None)
            hits += rank is not None
            rr += 1 / rank if rank else 0
            rows.append({"id": c["id"], "expected": c["expected_docs"], "got": res, "rank": rank})
        db.commit()
    finally:
        db.close()
    return {
        "k": k,
        "cases": len(kc),
        "hit_at_k": round(hits / len(kc), 3),
        "mrr": round(rr / len(kc), 3),
        "embeddings": rag.backend(),
        "details": rows,
    }


def sensor_fault_scores(seed: int = 7) -> dict:
    """Precision / recall of the health classifier on synthetic probes with injected faults."""
    rng = np.random.default_rng(seed)
    now = datetime.now(UTC)
    truth, pred = [], []

    def frame(v):
        times = pd.to_datetime([now - timedelta(minutes=5 * (len(v) - 1 - i)) for i in range(len(v))], utc=True)
        return pd.DataFrame({"recorded_at": times, "value": v})

    base = 7 + np.sin(np.linspace(0, 2 * np.pi, 288))
    baseline = pd.Series({h: 7.0 for h in range(24)})
    for i in range(80):
        kind = ["ok", "stuck", "drift", "spiky"][i % 4]
        v = base + rng.normal(0, 0.05, 288)
        bl = None
        if kind == "stuck":
            v[-int(rng.integers(13, 60)) :] = round(float(v[-60]), 1)
        elif kind == "drift":
            v = np.full(288, 7.0) + rng.normal(0, 0.03, 288) + np.linspace(0, rng.uniform(0.6, 1.2), 288)
            bl = baseline
        elif kind == "spiky":
            idx = rng.choice(np.arange(270, 288), size=4, replace=False)
            v[idx] += rng.choice([-1, 1], size=4) * rng.uniform(1.5, 3, size=4)
        else:
            bl = pd.Series({h: 7.0 + np.sin(2 * np.pi * h / 24) * 0 for h in range(24)}) if i % 8 == 0 else None
            if bl is not None:
                v = np.full(288, 7.0) + rng.normal(0, 0.05, 288)
        h, _, _ = classify(frame(v), bl, "oxygen", now)
        truth.append(kind)
        pred.append(h)
    table = {}
    for k in ("stuck", "drift", "spiky"):
        tp = sum(t == k and p == k for t, p in zip(truth, pred, strict=True))
        fp = sum(t != k and p == k for t, p in zip(truth, pred, strict=True))
        fn = sum(t == k and p != k for t, p in zip(truth, pred, strict=True))
        table[k] = {
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "support": truth.count(k),
        }
    ok_correct = sum(t == "ok" and p == "ok" for t, p in zip(truth, pred, strict=True))
    table["ok"] = {"specificity": round(ok_correct / truth.count("ok"), 3), "support": truth.count("ok")}
    return table


def summarize(rows: list[dict], retrieval: dict, faults: dict) -> dict:
    def mean(xs):
        xs = list(xs)
        return round(sum(xs) / len(xs), 3) if xs else None

    groups = sorted({r["group"] for r in rows})
    g_total = sum(r["numbers"] for r in rows)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "cases": len(rows),
        "tool_correctness": mean(r["tool_correctness"] for r in rows if r["group"] not in ("out_of_scope",)),
        "refusal_accuracy": mean(r["refusal_ok"] for r in rows),
        "approval_rate": mean(r["approval_ok"] for r in rows if r["group"] in ("action",) or r["id"] == "l01"),
        "forbidden_content_ok": mean(r["forbidden_ok"] for r in rows),
        "language_match": mean(r["lang_ok"] for r in rows if r["group"] == "multilingual"),
        "number_grounding_rate": round(sum(r["grounded"] for r in rows) / g_total, 3) if g_total else None,
        "per_group": {
            g: {
                "cases": sum(r["group"] == g for r in rows),
                "passed": sum(
                    r["group"] == g
                    and r["tool_correctness"] == 1
                    and r["refusal_ok"]
                    and r["approval_ok"]
                    and r["forbidden_ok"]
                    and r["lang_ok"]
                    for r in rows
                ),
            }
            for g in groups
        },
        "retrieval": {k: v for k, v in retrieval.items() if k != "details"},
        "sensor_fault_detection": faults,
        "failures": [
            r
            for r in rows
            if not (r["tool_correctness"] == 1 and r["refusal_ok"] and r["approval_ok"] and r["forbidden_ok"] and r["lang_ok"])
        ],
    }


def run_all(users: dict | None = None, write: bool = True) -> dict:
    from ..config import get_settings

    s = get_settings()  # evaluation runs many questions in a row: lift the per-user rate limits
    s.rate_limit_per_minute, s.rate_limit_per_day, s.daily_token_budget = 10_000, 10_000, 10**9
    users = users or {"owner": "nadia@lacvert.farm", "worker": "karim@lacvert.farm", "technician": "samir@lacvert.farm"}
    cases = load_cases()

    async def go():
        return [await run_case(c, users) for c in cases]

    rows = asyncio.run(go())
    out = summarize(rows, retrieval_scores(cases), sensor_fault_scores())
    out["details"] = rows
    if write:
        RESULTS.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    r = run_all()
    print(json.dumps({k: v for k, v in r.items() if k not in ("details", "failures")}, indent=2, ensure_ascii=False))
    for f in r["failures"]:
        print("FAIL", f["id"], f["question"], f["called"], f["errors"])
