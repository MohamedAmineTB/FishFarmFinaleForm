"""The agent loop: stream -> tool call -> execute -> feed the result back -> continue.

Limits: 5 tool rounds, LLM_MAX_OUTPUT_TOKENS (800) per call, 2,000 characters of input.
UI payloads (charts, risk cards, comparisons, sources, follow-up chips) are derived here from the
tool results, deterministically, so they are the same whatever the provider.
Every request is logged in `llm_requests`; usage per user and day in `llm_usage`.
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from ..config import get_settings
from ..db import session_scope
from ..deps import Ctx
from ..services.briefing import farm_tz, on_shift_at, team
from ..services.views import alerts_for, live_basins
from .mock import detect_lang
from .providers import LLMProvider, estimate_cost, get_provider
from .tools import TOOLS, ToolContext, run_tool, tools_for, wrap_result

PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"
PROMPT_VERSION = "2026-11-19.1"
MAX_INPUT = 2000
log = logging.getLogger("fishfarm.assistant")
HISTORY = 16


class LimitError(Exception):
    pass


def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def farm_index(ctx: Ctx, page: dict) -> str:
    """Compact context (< ~500 tokens): who is asking, where, and the basins with status and open alerts."""
    with session_scope() as db:
        tz = farm_tz(db, ctx.owner_id)
        basins = live_basins(db, ctx.owner_id)
        alerts = alerts_for(db, ctx.owner_id, resolved=False)
    now = datetime.now(UTC).astimezone(tz)
    lines = [f"USER ROLE: {ctx.role}", f"USER NAME: {ctx.user.name}", f"FARM LOCAL TIME: {now:%A %d %B %Y %H:%M} ({tz.key})"]
    if page:
        bits = [f"{k}={v}" for k, v in page.items() if v]
        lines.append("CURRENT PAGE: " + "; ".join(bits))
    lines.append("BASINS (id | name | species | status | open alerts):")
    for b in basins:
        n = sum(a["basin_id"] == b["id"] for a in alerts)
        lines.append(f"- {b['id']} | {b['name']} | {b['species_name']} | {b['status']} | {n}")
    crit = [b["name"] for b in basins if b["status"] == "critical"]
    if crit:
        lines.append(f"SAFETY: {', '.join(crit)} is in CRITICAL state. Mention it first.")
    if ctx.role != "owner":
        lines.append("This user is not the owner: do not discuss money; focus on water, alerts, probes and tasks.")
    return "\n".join(lines)


# ---------------- guardrails ----------------


def check_limits(ctx: Ctx) -> None:
    s = get_settings()
    with session_scope() as db:
        minute = db.execute(
            text("SELECT count(*) FROM llm_requests WHERE user_id = :u AND created_at > :a"),
            {"u": ctx.user.id, "a": datetime.now(UTC) - timedelta(minutes=1)},
        ).scalar()
        day = db.execute(
            text("SELECT requests, tokens FROM llm_usage WHERE user_id = :u AND day = current_date"), {"u": ctx.user.id}
        ).first()
    if minute >= s.rate_limit_per_minute:
        raise LimitError(
            f"You're asking quickly: wait a minute before the next question (limit {s.rate_limit_per_minute} per minute)."
        )
    if day and day[0] >= s.rate_limit_per_day:
        raise LimitError(f"You've reached today's limit of {s.rate_limit_per_day} questions. It resets tomorrow.")
    if day and day[1] >= s.daily_token_budget:
        raise LimitError("Today's assistant budget is used up. It resets tomorrow; the dashboard keeps working.")


# ---------------- UI payloads derived from tool results ----------------


def ui_payloads(name: str, args: dict, result: dict) -> list[dict]:
    out: list[dict] = []
    if name == "get_readings" and result.get("series"):
        warn = result.get("warning_level")
        metric = result["metric"]
        out.append(
            {
                "type": "chart",
                "basin": result["basin"],
                "basin_id": result.get("basin_id"),
                "metric": {"dissolved_oxygen": "do", "temperature": "temp", "ph": "ph"}[metric],
                "times": [p[0] for p in result["series"]],
                "values": [p[1] for p in result["series"]],
                "warn": warn if isinstance(warn, int | float) else (warn[1] if isinstance(warn, list) else None),
                "unit": result["unit"],
            }
        )
    elif name == "get_oxygen_prediction" and not args.get("basin_id"):
        cards = [
            {
                "name": p["basin"],
                "species": p.get("species", ""),
                "p": p["probability_pct"] / 100,
                "why": ", ".join(f"{f['label'].lower()} {f['value']} {f['unit']}".strip() for f in p.get("top_features", [])[:2]),
            }
            for p in result.get("predictions", [])
            if p.get("probability_pct") is not None
        ]
        if cards:
            out.append({"type": "risk", "cards": cards})
    elif name == "compare_basins":
        rows = [r for r in result.get("ranking", []) if r["value"] is not None]
        if rows:
            top = max(abs(r["value"]) for r in rows) or 1
            out.append(
                {
                    "type": "compare",
                    "rows": [
                        {
                            "name": r["basin"],
                            "v": max(0, r["value"]) / top,
                            "raw": f"{r['value']}{'%' if r['unit'] == '%' else ' ' + r['unit']}",
                        }
                        for r in rows
                    ],
                }
            )
    elif name == "simulate_scenario" and "before" in result:
        b, a = result["before"]["profit_eur"], result["after"]["profit_eur"]
        top = max(abs(a), abs(b)) or 1
        out.append(
            {
                "type": "compare",
                "rows": [
                    {"name": "Profit now", "v": max(0, b) / top, "raw": f"€{b:,}"},
                    {"name": "Profit after", "v": max(0, a) / top, "raw": f"€{a:,}"},
                ],
            }
        )
    elif name == "search_knowledge":
        for h in result.get("results", [])[:3]:
            out.append(
                {
                    "type": "source",
                    "title": h["title"],
                    "url": h["url"],
                    "publisher": h["publisher"],
                    "year": h["year"],
                    "doc_id": h["doc_id"],
                }
            )
    elif name in ("get_basin_status",) and result.get("thresholds", {}).get("source"):
        out.append(
            {
                "type": "source",
                "title": result["thresholds"]["source"],
                "url": "",
                "publisher": "",
                "year": None,
                "doc_id": "thresholds",
            }
        )
    return out


def result_summary(name: str, result: dict) -> str:
    if "error" in result:
        return f"error: {result['error']}"
    if name == "get_readings":
        return f"{result['points']} points, min {result['min']['value']} at {result['min']['at']}"
    if name == "get_alerts":
        return f"{result['count']} alerts"
    if name == "search_knowledge":
        return f"{len(result.get('results', []))} passages"
    if name == "get_sensor_health":
        return f"{len(result.get('problems', []))} probe problems"
    return "ok"


def followups(called: list[str], role: str, basin: str | None) -> list[str]:
    if role == "technician":
        base = ["Which sensors need calibration?", "Summarize open alerts"]
    elif role == "worker":
        base = ["What should I do first on this shift?", "Summarize open alerts"]
    else:
        base = ["What is my risk today?", "How can I raise revenue?"]
        if basin:
            base = ["What is my risk today?", f"What if I add 500 fish to {basin}?"]
        if "get_oxygen_prediction" in called and not basin:
            base = ["Why did oxygen drop last night?", "How can I raise revenue?"]
        if "get_financials" in called or "simulate_scenario" in called:
            base = ["What is my risk today?", "Compare margin per basin this quarter"]
    return base


def default_assignee(ctx: Ctx, title: str) -> str | None:
    with session_scope() as db:
        people = team(db, ctx.owner_id)
    low = title.lower()
    if any(w in low for w in ("probe", "sensor", "calibrat", "sonde")):
        p = next((x for x in people if x["role"] == "technician"), None)
    elif any(w in low for w in ("aerator", "tonight", "feed", "night")):
        p = next(
            (
                x
                for x in people
                if x["role"] == "worker" and x["shift_start"] and on_shift_at(x["shift_start"], x["shift_end"], 23)
            ),
            None,
        )
    else:
        p = next((x for x in people if x["role"] == "worker"), None)
    return p["name"] if p else None


# ---------------- conversation memory ----------------


def load_history(conv_id: uuid.UUID) -> tuple[list[dict], str | None]:
    with session_scope() as db:
        rows = db.execute(
            text(
                "SELECT role, content FROM messages WHERE conversation_id = :c AND role IN ('user','assistant') "
                "ORDER BY created_at"
            ),
            {"c": conv_id},
        ).all()
        summary = db.execute(text("SELECT summary FROM conversations WHERE id = :c"), {"c": conv_id}).scalar()
    msgs = [{"role": r, "content": [{"type": "text", "text": c.get("text") or "…"}]} for r, c in rows]
    if len(msgs) > HISTORY:
        older = [m["content"][0]["text"] for m in msgs[:-HISTORY] if m["role"] == "user"]
        summary = "Earlier in this conversation the user asked: " + " | ".join(q[:120] for q in older[-10:])
        msgs = msgs[-HISTORY:]
        if msgs and msgs[0]["role"] == "assistant":
            msgs = msgs[1:]
    return msgs, summary


def ensure_conversation(ctx: Ctx, conv_id: str | None, question: str) -> uuid.UUID:
    with session_scope() as db:
        if conv_id:
            row = db.execute(
                text("SELECT id FROM conversations WHERE id = :c AND user_id = :u"), {"c": conv_id, "u": ctx.user.id}
            ).scalar()
            if row:
                return row
        cid = uuid.uuid4()
        title = question.strip().split("\n")[0][:80]
        db.execute(
            text("INSERT INTO conversations (id, owner_user_id, user_id, title) VALUES (:i, :o, :u, :t)"),
            {"i": cid, "o": ctx.owner_id, "u": ctx.user.id, "t": title},
        )
        return cid


# ---------------- the turn ----------------


async def run_turn(
    ctx: Ctx, question: str, conv_id: str | None, page: dict, provider: LLMProvider | None = None, trace: list | None = None
) -> AsyncIterator[dict]:
    s = get_settings()
    t0 = time.monotonic()
    question = (question or "").strip()
    if not question:
        yield {"type": "error", "message": "Ask a question first."}
        return
    if len(question) > MAX_INPUT:
        yield {"type": "error", "message": f"Please keep questions under {MAX_INPUT} characters."}
        return
    try:
        check_limits(ctx)
    except LimitError as e:
        yield {"type": "error", "message": str(e), "code": "rate_limited"}
        return

    provider = provider or get_provider()
    cid = ensure_conversation(ctx, conv_id, question)
    history, summary = load_history(cid)
    lang = detect_lang(question)
    yield {
        "type": "meta",
        "conversation_id": str(cid),
        "provider": provider.name,
        "model": provider.model,
        "demo_mode": provider.name == "mock",
        "lang": lang,
        "dir": "rtl" if lang == "ar" else "ltr",
    }

    with session_scope() as db:
        tzname = farm_tz(db, ctx.owner_id).key
        db.execute(
            text(
                "INSERT INTO messages (conversation_id, owner_user_id, role, content) VALUES (:c, :o, 'user', CAST(:x AS jsonb))"
            ),
            {"c": cid, "o": ctx.owner_id, "x": json.dumps({"text": question, "page": page})},
        )
    tctx = ToolContext(
        owner_id=ctx.owner_id, user_id=ctx.user.id, role=ctx.role, permissions=ctx.permissions, tz=tzname, page=page
    )
    system = [
        {"type": "text", "text": system_prompt()},
        {"type": "text", "text": farm_index(ctx, page) + (f"\n{summary}" if summary else "")},
    ]
    tools = [t.schema() for t in tools_for(ctx.role)]
    messages = history + [{"role": "user", "content": [{"type": "text", "text": question}]}]

    answer, ui, called, approvals, retrieved = "", [], [], [], []
    seen_sources: set[str] = set()
    tokens_in = tokens_out = cache_read = 0
    status, basin_ctx = "ok", page.get("basin")
    try:
        for _round in range(s.llm_max_tool_iterations + 1):
            blocks: list[dict] = []
            text_buf = ""
            uses: list[dict] = []
            stop = "end_turn"
            async for ev in provider.stream_chat(
                system, messages, tools if _round < s.llm_max_tool_iterations else [], s.llm_max_output_tokens
            ):
                if ev["type"] == "text":
                    text_buf += ev["text"]
                    yield {"type": "token", "text": ev["text"]}
                elif ev["type"] == "tool_use":
                    uses.append(ev)
                elif ev["type"] == "usage":
                    tokens_in += ev["input"]
                    tokens_out += ev["output"]
                    cache_read += ev.get("cache_read", 0)
                elif ev["type"] == "stop":
                    stop = ev["reason"]
            if stop == "refusal":
                yield {
                    "type": "error",
                    "message": "The model declined to answer this request. Try rephrasing it about your farm.",
                }
                status = "refusal"
                break
            if text_buf:
                blocks.append({"type": "text", "text": text_buf})
                answer += text_buf
            for u in uses:
                blocks.append({"type": "tool_use", "id": u["id"], "name": u["name"], "input": u["input"]})
            messages.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "…"}]})
            if not uses:
                break
            results = []
            only_writes = all(TOOLS.get(u["name"]) and TOOLS[u["name"]].write for u in uses)
            for u in uses:
                tool = TOOLS.get(u["name"])
                if tool and tool.write:
                    # approval-gated: store the proposal, show an approval card, do not execute
                    if ctx.role == "worker" and u["name"] == "create_maintenance_task" and not ctx.can("maintenance"):
                        res = {"error": "Workers cannot create tasks; suggest it to the owner instead."}
                    else:
                        args = dict(u["input"] or {})
                        if u["name"] == "create_maintenance_task" and not args.get("assignee_name"):
                            args["assignee_name"] = default_assignee(ctx, args.get("title", ""))
                        aid = uuid.uuid4()
                        with session_scope() as db:
                            db.execute(
                                text(
                                    "INSERT INTO pending_actions (id, owner_user_id, user_id, tool, args) VALUES "
                                    "(:i, :o, :u, :t, CAST(:a AS jsonb))"
                                ),
                                {"i": aid, "o": ctx.owner_id, "u": ctx.user.id, "t": u["name"], "a": json.dumps(args)},
                            )
                        card = {"type": "approval_request", "id": str(aid), "tool": u["name"], **args}
                        approvals.append(card)
                        yield card
                        res = {"status": "waiting for the user's approval in the app", "action_id": str(aid)}
                    results.append({"type": "tool_result", "tool_use_id": u["id"], "content": wrap_result(res)})
                    continue
                label = tool.label(u["input"] or {}) if tool else u["name"]
                yield {"type": "tool_call", "id": u["id"], "name": u["name"], "label": label, "args": u["input"]}
                res, is_err = run_tool(tctx, u["name"], u["input"] or {})
                called.append(u["name"])
                if trace is not None:  # used by the evaluation suite (number grounding)
                    trace.append({"name": u["name"], "args": u["input"], "result": res, "error": is_err})
                if (u["input"] or {}).get("basin_id"):
                    basin_ctx = res.get("basin", basin_ctx)
                if u["name"] == "search_knowledge":
                    retrieved += [h["doc_id"] for h in res.get("results", [])]
                yield {
                    "type": "tool_result",
                    "id": u["id"],
                    "name": u["name"],
                    "summary": result_summary(u["name"], res),
                    "ok": not is_err,
                }
                for p in ui_payloads(u["name"], u["input"] or {}, res) if not is_err else []:
                    if p["type"] == "source":  # one chip per document
                        if p["doc_id"] in seen_sources:
                            continue
                        seen_sources.add(p["doc_id"])
                    ui.append(p)
                    yield p
                ui.append({"type": "data", "name": u["name"], "args": u["input"]})
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": u["id"],
                        "content": wrap_result(res),
                        **({"is_error": True} if is_err else {}),
                    }
                )
            messages.append({"role": "user", "content": results})
            if only_writes:
                break
    except Exception as e:  # provider or network failure: tell the user, log it
        status = "error"
        log.exception("assistant turn failed")
        yield {"type": "error", "message": f"The assistant is unavailable right now ({type(e).__name__}). Try again in a moment."}

    fu = followups(called, ctx.role, basin_ctx if isinstance(basin_ctx, str) else None)
    yield {"type": "followups", "items": fu}
    latency = int((time.monotonic() - t0) * 1000)
    cost = estimate_cost(provider.model, tokens_in, tokens_out, cache_read)
    mid = uuid.uuid4()
    with session_scope() as db:
        db.execute(
            text(
                "INSERT INTO messages (id, conversation_id, owner_user_id, role, content, tokens_in, tokens_out, model) "
                "VALUES (:i, :c, :o, 'assistant', CAST(:x AS jsonb), :ti, :to, :m)"
            ),
            {
                "i": mid,
                "c": cid,
                "o": ctx.owner_id,
                "ti": tokens_in,
                "to": tokens_out,
                "m": provider.model,
                "x": json.dumps(
                    {"text": answer, "ui": ui, "approvals": approvals, "followups": fu, "tools": called, "lang": lang},
                    default=str,
                ),
            },
        )
        db.execute(
            text("UPDATE pending_actions SET message_id = :m WHERE id = ANY(:ids)"),
            {"m": mid, "ids": [uuid.UUID(a["id"]) for a in approvals]},
        )
        db.execute(
            text("UPDATE conversations SET updated_at = now(), summary = coalesce(:s, summary) WHERE id = :c"),
            {"c": cid, "s": summary},
        )
        db.execute(
            text(
                "INSERT INTO llm_requests (owner_user_id, user_id, conversation_id, message_id, provider, model, "
                "prompt_version, latency_ms, tokens_in, tokens_out, cost_usd, tools, retrieved, status) VALUES "
                "(:o, :u, :c, :m, :p, :md, :pv, :l, :ti, :to, :cost, CAST(:tools AS jsonb), CAST(:r AS jsonb), :st)"
            ),
            {
                "o": ctx.owner_id,
                "u": ctx.user.id,
                "c": cid,
                "m": mid,
                "p": provider.name,
                "md": provider.model,
                "pv": PROMPT_VERSION,
                "l": latency,
                "ti": tokens_in,
                "to": tokens_out,
                "cost": cost,
                "tools": json.dumps(called),
                "r": json.dumps(retrieved),
                "st": status,
            },
        )
        db.execute(
            text(
                "INSERT INTO llm_usage (user_id, day, requests, tokens) VALUES (:u, current_date, 1, :t) "
                "ON CONFLICT (user_id, day) DO UPDATE SET requests = llm_usage.requests + 1, "
                "tokens = llm_usage.tokens + EXCLUDED.tokens"
            ),
            {"u": ctx.user.id, "t": tokens_in + tokens_out},
        )
    yield {
        "type": "done",
        "message_id": str(mid),
        "conversation_id": str(cid),
        "tokens": {"in": tokens_in, "out": tokens_out},
        "cost_usd": cost,
        "latency_ms": latency,
        "prompt_version": PROMPT_VERSION,
    }
