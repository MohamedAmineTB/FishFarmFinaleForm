"""Daily farm briefing, generated once per day (or on Refresh) and cached in `briefings`.

Template-based and deterministic: it works with or without an LLM.
"""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from ..db import session_scope
from ..services import briefing as br
from ..services.views import alerts_for, live_basins


def build(db, owner_id: uuid.UUID) -> dict:
    now = datetime.now(UTC)
    tz = br.farm_tz(db, owner_id)
    basins = live_basins(db, owner_id)
    alerts = alerts_for(db, owner_id, resolved=False)
    lows = br.overnight_lows(db, owner_id, now)
    tasks = br.tasks_json(db, owner_id, open_only=True)
    bullets = []
    crit = [b["name"] for b in basins if b["status"] == "critical"]
    if crit:
        bullets.append(f"CRITICAL: {', '.join(crit)} needs attention now.")
    bullets.append(
        f"{len(alerts)} open alert{'s' if len(alerts) != 1 else ''}"
        + (
            f" ({sum(a['kind'] == 'sensor' for a in alerts)} hardware, {sum(a['kind'] == 'water' for a in alerts)} water)."
            if alerts
            else "."
        )
    )
    for _bid, low in lows.items():
        if low["warn"] is not None and low["value"] < low["warn"]:
            t = datetime.fromisoformat(low["time"]).astimezone(tz)
            bullets.append(
                f"{low['basin']}: overnight oxygen low {low['value']:.2f} mg/L at {t:%H:%M}, "
                f"under the {low['warn']} mg/L warning level."
            )
    risky = [b for b in basins if (b["risk"] or 0) >= 0.3]
    for b in sorted(risky, key=lambda x: -x["risk"]):
        bullets.append(f"{b['name']}: {round(b['risk'] * 100)}% chance of low oxygen before dawn (estimate).")
    if tasks:
        bullets.append(
            f"{len(tasks)} maintenance task{'s' if len(tasks) != 1 else ''} open, "
            f"for example: {tasks[0]['title']} ({tasks[0]['who']}, due {tasks[0]['due']})."
        )
    actions = br.owner_actions(db, owner_id, now)
    return {
        "date": now.astimezone(tz).date().isoformat(),
        "generated_at": now.isoformat(),
        "bullets": bullets[:5],
        "top_actions": [{"title": a["title"], "detail": a["text"]} for a in actions],
        "overnight_lows": [
            {
                "basin": v["basin"],
                "value_mg_l": round(v["value"], 2),
                "at": datetime.fromisoformat(v["time"]).astimezone(tz).strftime("%H:%M"),
                "warning_mg_l": v["warn"],
            }
            for v in lows.values()
        ],
    }


def farm_briefing(owner_id: uuid.UUID, role: str = "owner", refresh: bool = False) -> dict:
    with session_scope() as db:
        tz = br.farm_tz(db, owner_id)
        day = datetime.now(UTC).astimezone(tz).date()
        if not refresh:
            row = db.execute(
                text("SELECT content FROM briefings WHERE owner_user_id = :o AND day = :d"), {"o": owner_id, "d": day}
            ).scalar()
            if row:
                return _for_role(row, role)
        content = build(db, owner_id)
        db.execute(
            text(
                "INSERT INTO briefings (owner_user_id, day, content) VALUES (:o, :d, CAST(:c AS jsonb)) "
                "ON CONFLICT (owner_user_id, day) DO UPDATE SET content = EXCLUDED.content, created_at = now()"
            ),
            {"o": owner_id, "d": day, "c": json.dumps(content)},
        )
        return _for_role(content, role)


def _for_role(content: dict, role: str) -> dict:
    if role == "owner":
        return content
    # workers and technicians get the shift briefing without money
    return {k: v for k, v in content.items() if k != "top_actions"} | {"note": "shift briefing"}
