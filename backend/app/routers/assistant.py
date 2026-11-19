"""Assistant API: SSE chat stream, conversations, approvals, feedback, briefing, AI Ops."""

import json
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ..assistant.agent import run_turn
from ..assistant.briefing_cache import farm_briefing
from ..db import get_db, notify
from ..deps import Ctx, current_ctx, require_owner
from ..models import Alert, Basin, Task, UserRole
from ..services.briefing import farm_tz

router = APIRouter(prefix="/api", tags=["assistant"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    page: dict = Field(default_factory=dict)


@router.post("/chat/stream")
async def chat_stream(body: ChatIn, request: Request, ctx: Ctx = Depends(current_ctx)):
    page = {k: str(v)[:80] for k, v in list(body.page.items())[:6]}

    async def events():
        async for ev in run_turn(ctx, body.message, body.conversation_id, page):
            if await request.is_disconnected():  # stop the loop when the user presses Stop or leaves
                break
            yield {"event": ev["type"], "data": json.dumps(ev, default=str, ensure_ascii=False)}

    return EventSourceResponse(events(), ping=15)


@router.get("/chat/conversations")
def conversations(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    rows = (
        db.execute(
            text("SELECT id, title, updated_at FROM conversations WHERE user_id = :u ORDER BY updated_at DESC LIMIT 20"),
            {"u": ctx.user.id},
        )
        .mappings()
        .all()
    )
    return [{"id": str(r["id"]), "title": r["title"], "updated_at": r["updated_at"].isoformat()} for r in rows]


@router.get("/chat/conversations/{conv_id}")
def conversation(conv_id: uuid.UUID, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    owner = db.execute(text("SELECT user_id FROM conversations WHERE id = :c"), {"c": conv_id}).scalar()
    if owner != ctx.user.id:
        raise HTTPException(404, "Conversation not found.")
    rows = (
        db.execute(
            text(
                "SELECT m.id, m.role, m.content, m.created_at, f.rating FROM messages m LEFT JOIN feedback f ON "
                "f.message_id = m.id AND f.user_id = :u WHERE m.conversation_id = :c AND m.role IN "
                "('user','assistant') ORDER BY m.created_at"
            ),
            {"c": conv_id, "u": ctx.user.id},
        )
        .mappings()
        .all()
    )
    statuses = {
        str(r["id"]): r["status"]
        for r in db.execute(text("SELECT id, status FROM pending_actions WHERE user_id = :u"), {"u": ctx.user.id}).mappings()
    }
    out = []
    for r in rows:
        c = dict(r["content"])
        for a in c.get("approvals", []):
            a["status"] = statuses.get(a["id"], "pending")
        out.append(
            {
                "id": str(r["id"]),
                "role": r["role"],
                "content": c,
                "rating": r["rating"],
                "created_at": r["created_at"].isoformat(),
            }
        )
    return out


def _due(label: str | None, today: date) -> tuple[date | None, str | None]:
    s = (label or "").strip().lower()
    if s in ("today", "tonight", "aujourd'hui", "ce soir", ""):
        return today, label or "Today"
    if s in ("tomorrow", "demain"):
        return today + timedelta(days=1), None
    try:
        return date.fromisoformat(s), None
    except ValueError:
        return today, label


@router.post("/chat/actions/{action_id}/{decision}")
def decide(action_id: uuid.UUID, decision: str, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    if decision not in ("approve", "cancel"):
        raise HTTPException(404, "Unknown decision.")
    row = (
        db.execute(text("SELECT * FROM pending_actions WHERE id = :i AND user_id = :u"), {"i": action_id, "u": ctx.user.id})
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(404, "Action not found.")
    if row["status"] != "pending":
        raise HTTPException(409, f"This action is already {row['status']}.")
    if decision == "cancel":
        db.execute(text("UPDATE pending_actions SET status = 'cancelled' WHERE id = :i"), {"i": action_id})
        db.commit()
        return {"status": "cancelled"}
    args = row["args"]
    result: dict
    if row["tool"] == "create_maintenance_task":
        if not (ctx.is_owner or ctx.can("maintenance")):
            raise HTTPException(403, "Only the owner or a technician can create tasks.")
        team = db.execute(
            text("SELECT u.id, u.name FROM users u JOIN user_roles r ON r.user_id = u.id WHERE r.owner_user_id = :o"),
            {"o": ctx.owner_id},
        ).all()
        who = next(
            (uid for uid, name in team if args.get("assignee_name") and name.lower() == args["assignee_name"].lower()), None
        )
        basin = None
        if args.get("basin_id"):
            ref = str(args["basin_id"]).lower()
            for b in db.query(Basin).filter(Basin.owner_user_id == ctx.owner_id):
                if str(b.id) == ref or b.name.lower() == ref:
                    basin = b
        today = datetime.now(UTC).astimezone(farm_tz(db, ctx.owner_id)).date()
        due, label = _due(args.get("due"), today)
        t = Task(
            owner_user_id=ctx.owner_id,
            title=args["title"][:200],
            assignee_user_id=who,
            basin_id=basin.id if basin else None,
            status="pending",
            source="assistant",
            due_date=due,
            due_label=label if label and label.lower() not in ("today",) else None,
            created_by=ctx.user.id,
        )
        db.add(t)
        db.flush()
        notify(
            db,
            {
                "type": "task",
                "action": "created",
                "owner_id": str(ctx.owner_id),
                "task_id": str(t.id),
                "assignee_id": str(who) if who else None,
            },
        )
        result = {"task_id": str(t.id), "assignee": args.get("assignee_name")}
    elif row["tool"] == "acknowledge_alert":
        a = db.get(Alert, uuid.UUID(str(args["alert_id"])))
        if not a or a.owner_user_id != ctx.owner_id:
            raise HTTPException(404, "Alert not found.")
        a.is_resolved, a.resolved_by, a.resolved_at, a.resolution_note = True, ctx.user.id, datetime.now(UTC), args["note"]
        db.execute(text("SELECT ff_refresh_basin_status(:b)"), {"b": a.basin_id})
        notify(db, {"type": "alert", "action": "resolved", "owner_id": str(ctx.owner_id), "alert_id": str(a.id)})
        result = {"alert_id": str(a.id)}
    else:
        raise HTTPException(422, "Unknown action.")
    db.execute(
        text("UPDATE pending_actions SET status = 'approved', result = CAST(:r AS jsonb) WHERE id = :i"),
        {"i": action_id, "r": json.dumps(result)},
    )
    db.commit()
    return {"status": "approved", **result}


class FeedbackIn(BaseModel):
    message_id: uuid.UUID
    rating: int = Field(ge=-1, le=1)
    reason: str | None = Field(None, max_length=500)


@router.post("/chat/feedback")
def feedback(body: FeedbackIn, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    if body.rating == 0:
        raise HTTPException(422, "Rating must be 1 or -1.")
    ok = db.execute(
        text("SELECT 1 FROM messages m JOIN conversations c ON c.id = m.conversation_id WHERE m.id = :m AND c.user_id = :u"),
        {"m": body.message_id, "u": ctx.user.id},
    ).first()
    if not ok:
        raise HTTPException(404, "Message not found.")
    db.execute(
        text(
            "INSERT INTO feedback (owner_user_id, user_id, message_id, rating, reason) VALUES (:o, :u, :m, :r, :why) "
            "ON CONFLICT (user_id, message_id) DO UPDATE SET rating = EXCLUDED.rating, "
            "reason = coalesce(EXCLUDED.reason, feedback.reason)"
        ),
        {"o": ctx.owner_id, "u": ctx.user.id, "m": body.message_id, "r": body.rating, "why": body.reason},
    )
    db.execute(text("UPDATE llm_requests SET feedback = :r WHERE message_id = :m"), {"r": body.rating, "m": body.message_id})
    db.commit()
    return {"ok": True}


@router.get("/briefing")
def briefing(refresh: bool = False, ctx: Ctx = Depends(current_ctx)):
    return farm_briefing(ctx.owner_id, ctx.role, refresh=refresh)


@router.get("/ai-ops")
def ai_ops(ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    """Owner-only observability of the assistant: usage, latency, cost, tools, feedback (last 14 days)."""
    since = datetime.now(UTC) - timedelta(days=14)
    p = {"o": ctx.owner_id, "a": since}
    per_day = (
        db.execute(
            text(
                "SELECT date_trunc('day', created_at)::date AS d, count(*) AS n, avg(latency_ms) AS lat, "
                "sum(cost_usd) AS cost FROM llm_requests WHERE owner_user_id = :o AND created_at > :a "
                "GROUP BY 1 ORDER BY 1"
            ),
            p,
        )
        .mappings()
        .all()
    )
    tot = (
        db.execute(
            text(
                "SELECT count(*) AS n, coalesce(avg(latency_ms), 0) AS lat, coalesce(sum(cost_usd), 0) AS cost, "
                "coalesce(sum(tokens_in + tokens_out), 0) AS tokens, count(*) FILTER (WHERE status <> 'ok') AS errors "
                "FROM llm_requests WHERE owner_user_id = :o AND created_at > :a"
            ),
            p,
        )
        .mappings()
        .first()
    )
    tools = (
        db.execute(
            text(
                "SELECT t AS name, count(*) AS n FROM llm_requests, jsonb_array_elements_text(tools) AS t "
                "WHERE owner_user_id = :o AND created_at > :a GROUP BY 1 ORDER BY 2 DESC LIMIT 8"
            ),
            p,
        )
        .mappings()
        .all()
    )
    fb = (
        db.execute(
            text(
                "SELECT count(*) FILTER (WHERE rating = 1) AS up, count(*) FILTER (WHERE rating = -1) AS down "
                "FROM feedback WHERE owner_user_id = :o AND created_at > :a"
            ),
            p,
        )
        .mappings()
        .first()
    )
    providers = (
        db.execute(
            text(
                "SELECT provider, model, count(*) AS n, sum(cost_usd) AS cost FROM llm_requests "
                "WHERE owner_user_id = :o AND created_at > :a GROUP BY 1, 2 ORDER BY 3 DESC"
            ),
            p,
        )
        .mappings()
        .all()
    )
    recent = (
        db.execute(
            text(
                "SELECT r.created_at, r.latency_ms, r.tokens_in + r.tokens_out AS tokens, r.cost_usd, r.tools, "
                "r.status, r.feedback, u.name FROM llm_requests r LEFT JOIN users u ON u.id = r.user_id "
                "WHERE r.owner_user_id = :o ORDER BY r.created_at DESC LIMIT 10"
            ),
            p,
        )
        .mappings()
        .all()
    )
    reasons = (
        db.execute(
            text(
                "SELECT reason, created_at FROM feedback WHERE owner_user_id = :o AND rating = -1 AND reason "
                "IS NOT NULL ORDER BY created_at DESC LIMIT 5"
            ),
            p,
        )
        .mappings()
        .all()
    )
    days = [(since.date() + timedelta(days=i + 1)) for i in range(14)]
    by = {r["d"]: r for r in per_day}
    up, down = fb["up"], fb["down"]
    members = db.query(UserRole).filter(UserRole.owner_user_id == ctx.owner_id).count()
    return {
        "days": [
            {
                "day": d.isoformat(),
                "requests": by[d]["n"] if d in by else 0,
                "latency_ms": round(by[d]["lat"]) if d in by else 0,
                "cost_usd": round(by[d]["cost"] or 0, 4) if d in by else 0,
            }
            for d in days
        ],
        "total": {
            "requests": tot["n"],
            "avg_latency_ms": round(tot["lat"]),
            "cost_usd": round(tot["cost"], 4),
            "tokens": tot["tokens"],
            "errors": tot["errors"],
            "users": members,
        },
        "tools": [dict(t) for t in tools],
        "feedback": {"up": up, "down": down, "up_rate": round(up / (up + down), 3) if up + down else None},
        "providers": [
            {"provider": r["provider"], "model": r["model"], "requests": r["n"], "cost_usd": round(r["cost"] or 0, 4)}
            for r in providers
        ],
        "recent": [
            {
                "at": r["created_at"].isoformat(),
                "user": r["name"],
                "latency_ms": r["latency_ms"],
                "tokens": r["tokens"],
                "cost_usd": r["cost_usd"],
                "tools": r["tools"],
                "status": r["status"],
                "feedback": r["feedback"],
            }
            for r in recent
        ],
        "negative_reasons": [{"reason": r["reason"], "at": r["created_at"].isoformat()} for r in reasons],
    }
