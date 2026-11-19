"""Typed, read-only tools of the farm assistant.

Security design:
- No tool takes an owner id. The farm comes from the signed-in user's JWT on the server and is
  set per transaction with set_config('app.owner_id', ...) after SET LOCAL ROLE ai_reader.
- ai_reader can only read the `ai` schema views; PostgreSQL row-level security limits every row
  to that farm. A basin id of another farm therefore returns "not found".
- Arguments are validated with Pydantic; validation errors are returned to the model as tool
  results so it can correct itself. Results are compact JSON with units and local times.
- Two write tools exist (create_maintenance_task, acknowledge_alert). The agent never runs them
  directly: it turns them into an approval card, and they run only when the user clicks Approve.
"""

import json
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..domain import SPECIES_NAMES, do_saturation_pct, load_thresholds
from . import rag

METRIC_TYPE = {
    "temperature": "temperature",
    "ph": "ph",
    "dissolved_oxygen": "oxygen",
    "oxygen": "oxygen",
    "do": "oxygen",
    "temp": "temperature",
}
UNIT = {"temperature": "°C", "ph": "", "oxygen": "mg/L"}
LABEL = {"temperature": "water temperature", "ph": "pH", "oxygen": "dissolved oxygen"}
MAX_RESULT_CHARS = 6000


class ToolError(Exception):
    pass


@dataclass
class ToolContext:
    owner_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    permissions: dict
    tz: str = "Europe/Paris"
    page: dict = field(default_factory=dict)

    def local(self, ts: datetime | None) -> str | None:
        if ts is None:
            return None
        return ts.astimezone(ZoneInfo(self.tz)).strftime("%a %d %b %H:%M")


@contextmanager
def ai_session(owner_id: uuid.UUID) -> Iterator[Session]:
    """Read-only, farm-scoped database session for tools (RLS through the ai_reader role)."""
    db = SessionLocal()
    try:
        db.execute(text("SET LOCAL ROLE ai_reader"))
        db.execute(text("SELECT set_config('app.owner_id', :o, true)"), {"o": str(owner_id)})
        db.execute(text("SET LOCAL statement_timeout = '15s'"))
        yield db
    finally:
        db.rollback()
        db.close()


# ---------------- helpers ----------------


def _basins(db: Session) -> list:
    return db.execute(text("SELECT * FROM ai.basins ORDER BY position, name")).mappings().all()


def resolve_basin(db: Session, ref: str | None):
    """Accepts a basin id, a name ('Basin 3') or a short form ('basin_3', '3'). Unknown or other farm -> not found."""
    if not ref:
        raise ToolError("basin_id is required")
    bs = _basins(db)
    r = str(ref).strip().lower().replace("_", " ")
    for b in bs:
        if str(b["id"]) == str(ref).strip() or b["name"].lower() == r:
            return b
    digits = "".join(ch for ch in r if ch.isdigit())
    if digits:
        for b in bs:
            if "".join(ch for ch in b["name"] if ch.isdigit()) == digits:
                return b
    raise ToolError(f"Basin '{ref}' not found on this farm.")


def _sensors(db: Session, basin_id) -> dict:
    rows = db.execute(text("SELECT * FROM ai.sensors WHERE basin_id = :b"), {"b": basin_id}).mappings().all()
    return {r["type"]: r for r in rows}


def _round(v, d=2):
    return None if v is None else round(float(v), d)


def _thr(db: Session, species: str) -> dict:
    t = load_thresholds(db)[species]
    return {
        "species": SPECIES_NAMES[species],
        "oxygen_warning_mg_l": t.do_warn,
        "oxygen_critical_mg_l": t.do_crit,
        "temperature_range_c": [t.temp_min, t.temp_max],
        "ph_range": [t.ph_min, t.ph_max],
        "source": t.sources.get("oxygen", {}).get("label"),
        "verified": t.sources.get("oxygen", {}).get("verified"),
    }


def _require_owner(ctx: ToolContext) -> None:
    if ctx.role != "owner":
        raise ToolError("Financial data is only available to the farm owner.")


# ---------------- argument models ----------------


class NoArgs(BaseModel):
    pass


class BasinArg(BaseModel):
    basin_id: str = Field(description="Basin id or name from the farm index, e.g. 'Basin 3'")


class OptBasinArg(BaseModel):
    basin_id: str | None = Field(None, description="Basin id or name; omit for every basin")


class ReadingsArgs(BaseModel):
    basin_id: str
    metric: Literal["temperature", "ph", "dissolved_oxygen"]
    start: datetime | None = Field(None, description="ISO time; default 24 hours ago")
    end: datetime | None = Field(None, description="ISO time; default now")
    aggregate: Literal["raw", "hourly", "daily"] = "raw"


class AlertsArgs(BaseModel):
    basin_id: str | None = None
    status: Literal["open", "resolved", "all"] = "open"
    limit: int = Field(10, ge=1, le=50)


class MaintenanceArgs(BaseModel):
    basin_id: str | None = None
    upcoming_only: bool = True
    limit: int = Field(10, ge=1, le=50)


class FinancialsArgs(BaseModel):
    basin_id: str | None = None
    period: Literal["month", "quarter", "year"] = "quarter"


class KnowledgeArgs(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    species: Literal["tilapia", "rainbow_trout", "common_carp", "sea_bass", "sea_bream", "atlantic_salmon"] | None = None


class CompareArgs(BaseModel):
    metric: Literal["avg_oxygen", "min_oxygen", "alerts", "margin", "cost_per_fish", "profit_per_fish"]
    period: Literal["day", "week", "month", "quarter"] = "day"


class ScenarioArgs(BaseModel):
    basin_id: str
    feed_cost_pct: float | None = Field(None, ge=-90, le=200, description="change of feeding cost in %")
    add_fish: int | None = Field(None, ge=-1_000_000, le=1_000_000, description="fish to add (negative to remove)")
    sale_price_pct: float | None = Field(None, ge=-90, le=200, description="change of sale price in %")
    fcr: float | None = Field(None, gt=0.5, le=5, description="new feed conversion ratio (current assumed 1.6)")
    mortality_pct: float | None = Field(None, ge=0, le=100)


class BriefingArgs(BaseModel):
    day: date | None = Field(None, description="day of the briefing; default today")


class TaskArgs(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    assignee_name: str | None = Field(None, description="team member name; default the technician or worker on duty")
    basin_id: str | None = None
    due: str = Field("Today", max_length=40, description="e.g. Today, Tonight, Tomorrow or a date")


class AckArgs(BaseModel):
    alert_id: str
    note: str = Field(min_length=1, max_length=500)


# ---------------- tools ----------------


def list_basins(ctx: ToolContext, db: Session, a: NoArgs) -> dict:
    out = []
    for b in _basins(db):
        s = _sensors(db, b["id"])
        do, t, ph = (s.get(k, {}).get("last_value") for k in ("oxygen", "temperature", "ph"))
        n = db.execute(text("SELECT count(*) FROM ai.alerts WHERE basin_id = :b AND NOT is_resolved"), {"b": b["id"]}).scalar()
        out.append(
            {
                "id": str(b["id"]),
                "name": b["name"],
                "species": SPECIES_NAMES[b["species"]],
                "status": b["status"],
                "oxygen_mg_l": _round(do),
                "temperature_c": _round(t, 1),
                "ph": _round(ph),
                "oxygen_saturation_pct": _round(do_saturation_pct(do, t), 0) if do and t else None,
                "open_alerts": n,
            }
        )
    return {"basins": out, "as_of": ctx.local(datetime.now(UTC))}


def get_basin_status(ctx: ToolContext, db: Session, a: BasinArg) -> dict:
    b = resolve_basin(db, a.basin_id)
    s = _sensors(db, b["id"])
    live = {}
    for typ in ("oxygen", "temperature", "ph"):
        r = s.get(typ)
        if r:
            live[typ] = {
                "value": _round(r["last_value"]),
                "unit": UNIT[typ],
                "at": ctx.local(r["last_reading_at"]),
                "probe": r["code"],
                "probe_health": r["health"],
            }
    do, t = live.get("oxygen", {}).get("value"), live.get("temperature", {}).get("value")
    alerts = (
        db.execute(
            text(
                "SELECT title, severity, kind, created_at FROM ai.alerts WHERE basin_id = :b AND NOT is_resolved "
                "ORDER BY created_at DESC LIMIT 5"
            ),
            {"b": b["id"]},
        )
        .mappings()
        .all()
    )
    last_m = (
        db.execute(
            text(
                "SELECT work_type, description, created_at FROM ai.maintenance m JOIN ai.sensors s "
                "ON s.id = m.sensor_id WHERE s.basin_id = :b ORDER BY m.created_at DESC LIMIT 1"
            ),
            {"b": b["id"]},
        )
        .mappings()
        .first()
    )
    return {
        "basin": b["name"],
        "id": str(b["id"]),
        "species": SPECIES_NAMES[b["species"]],
        "status": b["status"],
        "live": live,
        "oxygen_saturation_pct": _round(do_saturation_pct(do, t), 0) if do and t else None,
        "thresholds": _thr(db, b["species"]),
        "fish": b["fish_count"],
        "volume_m3": b["capacity"],
        "open_alerts": [
            {"title": x["title"], "severity": x["severity"], "kind": x["kind"], "at": ctx.local(x["created_at"])} for x in alerts
        ],
        "last_maintenance": (
            {"work": last_m["work_type"], "note": last_m["description"][:200], "at": ctx.local(last_m["created_at"])}
            if last_m
            else None
        ),
    }


def get_readings(ctx: ToolContext, db: Session, a: ReadingsArgs) -> dict:
    b = resolve_basin(db, a.basin_id)
    typ = METRIC_TYPE[a.metric]
    s = _sensors(db, b["id"]).get(typ)
    if not s:
        raise ToolError("This basin has no probe for that metric.")
    end = a.end or datetime.now(UTC)
    start = a.start or end - timedelta(hours=24)
    if end - start > timedelta(days=30):
        raise ToolError("The longest range is 30 days.")
    span = (end - start).total_seconds()
    if a.aggregate == "daily":
        bucket = 86400
    elif a.aggregate == "hourly":
        bucket = 3600
    else:
        bucket = max(300, int(span / 200))  # at most 200 points
    rows = db.execute(
        text(
            "SELECT to_timestamp(floor(extract(epoch FROM recorded_at) / :bk) * :bk) AS ts, avg(value) AS v, "
            "min(value) AS lo, max(value) AS hi FROM ai.readings WHERE sensor_id = :s AND recorded_at BETWEEN :a AND :e "
            "GROUP BY 1 ORDER BY 1"
        ),
        {"bk": bucket, "s": s["id"], "a": start, "e": end},
    ).all()
    if not rows:
        raise ToolError("No readings in that period.")
    vals = [float(r.v) for r in rows]
    i_min = min(range(len(rows)), key=lambda i: rows[i].lo)
    i_max = max(range(len(rows)), key=lambda i: rows[i].hi)
    th = _thr(db, b["species"])
    return {
        "basin": b["name"],
        "basin_id": str(b["id"]),
        "metric": a.metric,
        "unit": UNIT[typ],
        "period": {"from": ctx.local(start), "to": ctx.local(end)},
        "points": len(rows),
        "min": {"value": _round(rows[i_min].lo), "at": ctx.local(rows[i_min].ts)},
        "max": {"value": _round(rows[i_max].hi), "at": ctx.local(rows[i_max].ts)},
        "mean": _round(sum(vals) / len(vals)),
        "latest": {"value": _round(s["last_value"]), "at": ctx.local(s["last_reading_at"])},
        "warning_level": th["oxygen_warning_mg_l"]
        if typ == "oxygen"
        else (th["ph_range"] if typ == "ph" else th["temperature_range_c"]),
        "series": [[r.ts.isoformat(), round(float(r.v), 3)] for r in rows],
    }


def get_alerts(ctx: ToolContext, db: Session, a: AlertsArgs) -> dict:
    q = "SELECT al.*, b.name AS basin FROM ai.alerts al JOIN ai.basins b ON b.id = al.basin_id WHERE true"
    p: dict = {"l": a.limit}
    if a.basin_id:
        q += " AND al.basin_id = :b"
        p["b"] = resolve_basin(db, a.basin_id)["id"]
    if a.status != "all":
        q += " AND al.is_resolved = :r"
        p["r"] = a.status == "resolved"
    if ctx.role == "worker":
        q += " AND al.kind = 'water'"
    elif ctx.role == "technician":
        q += " AND al.kind = 'sensor'"
    rows = db.execute(text(q + " ORDER BY al.created_at DESC LIMIT :l"), p).mappings().all()
    sev = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    rows = sorted(rows, key=lambda r: (-sev[r["severity"]], -r["created_at"].timestamp()))
    return {
        "count": len(rows),
        "alerts": [
            {
                "id": str(r["id"]),
                "basin": r["basin"],
                "title": r["title"],
                "description": r["description"],
                "severity": r["severity"],
                "kind": "hardware" if r["kind"] == "sensor" else "water",
                "routed_to": "technician" if r["kind"] == "sensor" else "worker on shift",
                "value": _round(r["value"]),
                "at": ctx.local(r["created_at"]),
                "resolved": r["is_resolved"],
                "resolution_note": r["resolution_note"],
            }
            for r in rows
        ],
    }


def get_maintenance(ctx: ToolContext, db: Session, a: MaintenanceArgs) -> dict:
    p: dict = {"l": a.limit}
    q = (
        "SELECT t.title, t.status, t.due_date, t.source, tm.name AS assignee, b.name AS basin FROM ai.tasks t "
        "LEFT JOIN ai.team tm ON tm.user_id = t.assignee_user_id LEFT JOIN ai.basins b ON b.id = t.basin_id WHERE true"
    )
    if a.basin_id:
        q += " AND t.basin_id = :b"
        p["b"] = resolve_basin(db, a.basin_id)["id"]
    if a.upcoming_only:
        q += " AND t.status <> 'fixed'"
    tasks = db.execute(text(q + " ORDER BY t.due_date NULLS LAST LIMIT :l"), p).mappings().all()
    logs = (
        db.execute(
            text(
                "SELECT m.work_type, m.description, m.created_at, s.code FROM ai.maintenance m "
                "LEFT JOIN ai.sensors s ON s.id = m.sensor_id ORDER BY m.created_at DESC LIMIT 5"
            )
        )
        .mappings()
        .all()
    )
    return {
        "tasks": [
            {
                "title": t["title"],
                "status": t["status"].replace("_", " "),
                "due": str(t["due_date"]) if t["due_date"] else None,
                "assignee": t["assignee"],
                "basin": t["basin"],
            }
            for t in tasks
        ],
        "recent_logs": [
            {"work": m["work_type"], "probe": m["code"], "note": m["description"][:200], "at": ctx.local(m["created_at"])}
            for m in logs
        ],
    }


def _fin_row(b, factor: float) -> dict:
    cost = (b["feeding_cost"] + b["maintenance_cost"] + b["operational_cost"]) * factor
    rev = b["revenue"] * factor
    return {
        "basin": b["name"],
        "revenue_eur": round(rev),
        "costs_eur": round(cost),
        "profit_eur": round(rev - cost),
        "margin_pct": round(100 * (rev - cost) / rev, 1) if rev else None,
        "feed_share_pct": round(100 * b["feeding_cost"] * factor / cost, 1) if cost else None,
        "profit_per_fish_eur": round((rev - cost) / b["fish_count"], 2) if b["fish_count"] else None,
        "fish": b["fish_count"],
    }


def get_financials(ctx: ToolContext, db: Session, a: FinancialsArgs) -> dict:
    _require_owner(ctx)
    factor = {"quarter": 1.0, "month": 1 / 3, "year": 4.0}[a.period]
    bs = [resolve_basin(db, a.basin_id)] if a.basin_id else _basins(db)
    rows = [_fin_row(b, factor) for b in bs]
    tot_rev = sum(r["revenue_eur"] for r in rows)
    tot_cost = sum(r["costs_eur"] for r in rows)
    feed = sum(b["feeding_cost"] * factor for b in bs)
    return {
        "period": a.period,
        "note": "Stored figures are for the current quarter; month and year are pro-rated estimates."
        if a.period != "quarter"
        else "Current quarter.",
        "basins": rows,
        "total": {
            "revenue_eur": round(tot_rev),
            "costs_eur": round(tot_cost),
            "profit_eur": round(tot_rev - tot_cost),
            "margin_pct": round(100 * (tot_rev - tot_cost) / tot_rev, 1) if tot_rev else None,
            "feed_share_pct": round(100 * feed / tot_cost, 1) if tot_cost else None,
            "cost_per_basin_eur": round(tot_cost / len(rows)) if rows else None,
        },
    }


def get_oxygen_prediction(ctx: ToolContext, db: Session, a: OptBasinArg) -> dict:
    bs = [resolve_basin(db, a.basin_id)] if a.basin_id else _basins(db)
    out = []
    for b in bs:
        p = (
            db.execute(text("SELECT * FROM ai.predictions WHERE basin_id = :b ORDER BY created_at DESC LIMIT 1"), {"b": b["id"]})
            .mappings()
            .first()
        )
        th = _thr(db, b["species"])
        if not p:
            out.append({"basin": b["name"], "probability": None, "note": "no prediction yet"})
            continue
        out.append(
            {
                "basin": b["name"],
                "basin_id": str(b["id"]),
                "species": th["species"],
                "probability_pct": round(100 * p["probability"]),
                "event": f"oxygen below {th['oxygen_warning_mg_l']} mg/L {p['horizon']}",
                "top_features": [{"label": f["label"], "value": f["value"], "unit": f["unit"]} for f in p["top_features"]],
                "model_version": p["model_version"],
                "computed_at": ctx.local(p["created_at"]),
                "is_estimate": True,
            }
        )
    return {"predictions": out, "is_estimate": True}


def search_knowledge(ctx: ToolContext, db: Session, a: KnowledgeArgs) -> dict:
    hits = rag.search(db, a.query, a.species, k=4)
    return {
        "results": [
            {
                "doc_id": h["doc_id"],
                "title": h["title"],
                "section": h["section"],
                "url": h["url"],
                "publisher": h["publisher"],
                "year": h["year"],
                "text": h["text"],
            }
            for h in hits
        ]
    }


def get_sensor_health(ctx: ToolContext, db: Session, a: OptBasinArg) -> dict:
    q = "SELECT s.*, b.name AS basin FROM ai.sensors s JOIN ai.basins b ON b.id = s.basin_id"
    p = {}
    if a.basin_id:
        q += " WHERE s.basin_id = :b"
        p["b"] = resolve_basin(db, a.basin_id)["id"]
    rows = db.execute(text(q + " ORDER BY s.code"), p).mappings().all()
    out = []
    for s in rows:
        problem = s["health"] != "ok"
        out.append(
            {
                "probe": s["code"],
                "basin": s["basin"],
                "measures": LABEL[s["type"]],
                "status": s["health"],
                "evidence": s["health_note"],
                "last_value": _round(s["last_value"]),
                "last_calibrated": ctx.local(s["last_calibrated_at"]),
                "classification": "sensor problem -> technician" if problem else "reads normally",
            }
        )
    return {
        "probes": out,
        "problems": [o for o in out if o["status"] != "ok"],
        "method": "rolling statistics on the last 24 h: flat line (stuck), jumps (spiky), offset from the probe's "
        "7-day baseline (drift), missing data (offline)",
    }


def compare_basins(ctx: ToolContext, db: Session, a: CompareArgs) -> dict:
    if a.metric in ("margin", "cost_per_fish", "profit_per_fish"):
        _require_owner(ctx)
    days = {"day": 1, "week": 7, "month": 30, "quarter": 90}[a.period]
    since = datetime.now(UTC) - timedelta(days=days)
    out = []
    for b in _basins(db):
        if a.metric in ("avg_oxygen", "min_oxygen"):
            fn = "avg" if a.metric == "avg_oxygen" else "min"
            v = db.execute(
                text(
                    f"SELECT {fn}(r.value) FROM ai.readings r JOIN ai.sensors s ON s.id = r.sensor_id "
                    "WHERE s.basin_id = :b AND s.type = 'oxygen' AND r.recorded_at > :a"
                ),
                {"b": b["id"], "a": since},
            ).scalar()
            out.append({"basin": b["name"], "value": _round(v), "unit": "mg/L"})
        elif a.metric == "alerts":
            v = db.execute(
                text("SELECT count(*) FROM ai.alerts WHERE basin_id = :b AND created_at > :a"), {"b": b["id"], "a": since}
            ).scalar()
            out.append({"basin": b["name"], "value": v, "unit": "alerts"})
        else:
            r = _fin_row(b, 1.0)
            key = {"margin": "margin_pct", "cost_per_fish": None, "profit_per_fish": "profit_per_fish_eur"}[a.metric]
            if key:
                out.append({"basin": b["name"], "value": r[key], "unit": "%" if key == "margin_pct" else "€"})
            else:
                out.append(
                    {
                        "basin": b["name"],
                        "value": round(r["costs_eur"] / b["fish_count"], 2) if b["fish_count"] else None,
                        "unit": "€",
                    }
                )
    out.sort(key=lambda x: (x["value"] is None, -(x["value"] or 0)))
    return {
        "metric": a.metric,
        "period": a.period if a.metric in ("avg_oxygen", "min_oxygen", "alerts") else "quarter",
        "ranking": out,
    }


def simulate_scenario(ctx: ToolContext, db: Session, a: ScenarioArgs) -> dict:
    """Deterministic what-if: same growth and price per fish as now unless changed."""
    _require_owner(ctx)
    b = resolve_basin(db, a.basin_id)
    fish0 = b["fish_count"] or 1
    rev0, feed0 = b["revenue"], b["feeding_cost"]
    other = b["maintenance_cost"] + b["operational_cost"]
    fish = max(0, fish0 + (a.add_fish or 0))
    survival = 1 - (a.mortality_pct or 0) / 100
    price = 1 + (a.sale_price_pct or 0) / 100
    rev = rev0 / fish0 * fish * survival * price
    feed = feed0 / fish0 * fish * (1 + (a.feed_cost_pct or 0) / 100) * ((a.fcr / 1.6) if a.fcr else 1)
    profit0, profit = rev0 - feed0 - other, rev - feed - other
    out = {
        "basin": b["name"],
        "is_estimate": True,
        "assumptions": "same revenue and feed per fish as this quarter; maintenance and operational costs unchanged; "
        "current FCR assumed 1.6",
        "changes": a.model_dump(exclude_none=True, exclude={"basin_id"}),
        "before": {
            "fish": fish0,
            "revenue_eur": round(rev0),
            "feed_cost_eur": round(feed0),
            "profit_eur": round(profit0),
            "density_fish_per_m3": round(fish0 / b["capacity"], 1),
        },
        "after": {
            "fish": fish,
            "revenue_eur": round(rev),
            "feed_cost_eur": round(feed),
            "profit_eur": round(profit),
            "density_fish_per_m3": round(fish / b["capacity"], 1),
        },
        "profit_change_eur": round(profit - profit0),
    }
    risks = []
    if (a.add_fish or 0) > 0:
        risks.append("More fish use more oxygen at night: watch the pre-dawn low for a week after stocking.")
        alert = db.execute(
            text("SELECT title FROM ai.alerts WHERE basin_id = :b AND metric = 'oxygen' AND NOT is_resolved"), {"b": b["id"]}
        ).scalar()
        if alert:
            risks.append(f"This basin already has an open oxygen alert ({alert}): fix the night oxygen first.")
    if (a.feed_cost_pct or 0) < 0:
        risks.append("Cheaper feed can mean a worse FCR: check growth on a weighed sample.")
    out["risks"] = risks
    return out


def get_farm_briefing(ctx: ToolContext, db: Session, a: BriefingArgs) -> dict:
    """Pre-computed daily summary (deterministic service code, cached once per day in `briefings`)."""
    from .briefing_cache import farm_briefing

    return farm_briefing(ctx.owner_id, ctx.role, refresh=False)


# write tools: described to the model, never executed by the agent itself
def create_maintenance_task(ctx: ToolContext, db: Session, a: TaskArgs) -> dict:
    raise ToolError("Write tools run only after approval.")


def acknowledge_alert(ctx: ToolContext, db: Session, a: AckArgs) -> dict:
    raise ToolError("Write tools run only after approval.")


@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable
    label: Callable[[dict], str]
    write: bool = False

    def schema(self) -> dict:
        s = self.args.model_json_schema()
        s.pop("title", None)
        for p in s.get("properties", {}).values():
            p.pop("title", None)
        return {"name": self.name, "description": self.description, "input_schema": s}


def _b(args: dict) -> str:
    b = args.get("basin_id")
    return str(b) if b else "all basins"


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "list_basins",
            "List every basin with species, status, latest oxygen/temperature/pH and open alert count.",
            NoArgs,
            list_basins,
            lambda a: "Listing basins",
        ),
        Tool(
            "get_basin_status",
            "Latest readings (with oxygen % saturation), species thresholds, open alerts and last maintenance of one basin.",
            BasinArg,
            get_basin_status,
            lambda a: f"Checking {_b(a)} status",
        ),
        Tool(
            "get_readings",
            "Readings of one metric for one basin: min/max/mean with times and a series (max 200 points, "
            "max 30 days). Default: last 24 hours.",
            ReadingsArgs,
            get_readings,
            lambda a: f"Reading {_b(a)} {a.get('metric', '').replace('_', ' ')}",
        ),
        Tool(
            "get_alerts",
            "Alerts of the farm (open, resolved or all), most severe first.",
            AlertsArgs,
            get_alerts,
            lambda a: "Reading alerts",
        ),
        Tool(
            "get_maintenance",
            "Maintenance tasks and recent maintenance logs.",
            MaintenanceArgs,
            get_maintenance,
            lambda a: "Reading maintenance tasks",
        ),
        Tool(
            "get_financials",
            "Revenue, costs, profit, margin, feed share and profit per fish per basin (owner only).",
            FinancialsArgs,
            get_financials,
            lambda a: f"Reading finances ({a.get('period', 'quarter')})",
        ),
        Tool(
            "get_oxygen_prediction",
            "Machine-learning estimate of the chance that oxygen falls below the species warning "
            "level before 06:00, with the main features. Always an estimate.",
            OptBasinArg,
            get_oxygen_prediction,
            lambda a: f"Reading oxygen prediction ({_b(a)})",
        ),
        Tool(
            "search_knowledge",
            "Search the farm's fish-farming knowledge base (FAO, UF/IFAS, SRAC, OMAFRA notes). Returns "
            "passages with title and url to cite.",
            KnowledgeArgs,
            search_knowledge,
            lambda a: f"Searching knowledge: {a.get('query', '')[:40]}",
        ),
        Tool(
            "get_sensor_health",
            "Probe health from rolling statistics (ok, stuck, drift, spiky, offline) with evidence; "
            "tells a sensor problem (technician) from a water problem (worker).",
            OptBasinArg,
            get_sensor_health,
            lambda a: f"Checking probe health ({_b(a)})",
        ),
        Tool(
            "compare_basins",
            "Rank basins on one metric (average or minimum oxygen, alert count, margin, cost or profit per fish).",
            CompareArgs,
            compare_basins,
            lambda a: f"Comparing basins: {a.get('metric', '')}",
        ),
        Tool(
            "simulate_scenario",
            "Deterministic what-if for one basin: change feed cost %, add fish, sale price %, FCR, "
            "mortality %. Returns before/after costs, revenue, profit and density (owner only). Always an estimate.",
            ScenarioArgs,
            simulate_scenario,
            lambda a: f"Simulating a scenario for {_b(a)}",
        ),
        Tool(
            "get_farm_briefing",
            "Today's pre-computed farm briefing: open problems, overnight oxygen lows, predictions, "
            "maintenance due and the top 3 actions.",
            BriefingArgs,
            get_farm_briefing,
            lambda a: "Reading today's briefing",
        ),
        Tool(
            "create_maintenance_task",
            "Propose a task for a team member (for example run an aerator, recalibrate a probe). "
            "The user must approve it in the app before it is created.",
            TaskArgs,
            create_maintenance_task,
            lambda a: "Preparing a task for approval",
            write=True,
        ),
        Tool(
            "acknowledge_alert",
            "Propose to mark an alert as handled with a note. The user must approve it in the app.",
            AckArgs,
            acknowledge_alert,
            lambda a: "Preparing an alert acknowledgement for approval",
            write=True,
        ),
    ]
}


def tools_for(role: str) -> list[Tool]:
    owner_only = {"get_financials", "simulate_scenario"}
    return [t for t in TOOLS.values() if role == "owner" or t.name not in owner_only]


def run_tool(ctx: ToolContext, name: str, args: dict) -> tuple[dict, bool]:
    """Executes a read tool in a farm-scoped read-only session. Returns (result, is_error)."""
    tool = TOOLS.get(name)
    if not tool:
        return {"error": f"Unknown tool {name}"}, True
    if tool.write:
        return {"error": "Write tools need the user's approval."}, True
    try:
        parsed = tool.args.model_validate(args or {})
    except ValidationError as e:
        return {"error": "Invalid arguments", "details": json.loads(e.json(include_url=False))[:5]}, True
    try:
        if name == "search_knowledge":  # the knowledge base is public, not farm data
            db = SessionLocal()
            try:
                return tool.fn(ctx, db, parsed), False
            finally:
                db.close()
        with ai_session(ctx.owner_id) as db:
            return tool.fn(ctx, db, parsed), False
    except ToolError as e:
        return {"error": str(e)}, True


def wrap_result(result: dict) -> str:
    """Tool output goes back to the model as data, clearly marked, and size-limited."""
    s = json.dumps(result, default=str, ensure_ascii=False)
    if len(s) > MAX_RESULT_CHARS:
        if "series" in result:
            r = dict(result)
            step = max(1, len(r["series"]) // 60)
            r["series"] = r["series"][::step]
            s = json.dumps(r, default=str, ensure_ascii=False)
        s = s[:MAX_RESULT_CHARS]
    return f"<tool_data>\n{s}\n</tool_data>"
