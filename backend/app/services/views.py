"""Read models: queries and JSON shapes shared by several endpoints (and the assistant tools)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..domain import (
    METRIC_INFO,
    SPECIES_NAMES,
    TYPE_TO_METRIC,
    Thresholds,
    do_saturation_pct,
    load_thresholds,
    value_class,
)
from ..models import Alert, Basin, Prediction, Sensor, User

SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
STEP = timedelta(minutes=15)
N_POINTS = 97  # 24 h at 15-minute steps, like the prototype


def basins_with_sensors(db: Session, owner_id: uuid.UUID) -> list[tuple[Basin, dict[str, Sensor]]]:
    basins = db.scalars(select(Basin).where(Basin.owner_user_id == owner_id).order_by(Basin.position, Basin.name)).all()
    sensors = db.scalars(select(Sensor).where(Sensor.owner_user_id == owner_id).order_by(Sensor.code)).all()
    by: dict[uuid.UUID, dict[str, Sensor]] = {}
    for s in sensors:
        by.setdefault(s.basin_id, {})[TYPE_TO_METRIC[s.type]] = s
    return [(b, by.get(b.id, {})) for b in basins]


def latest_predictions(db: Session, owner_id: uuid.UUID) -> dict[uuid.UUID, Prediction]:
    rows = db.scalars(
        text(
            "SELECT DISTINCT ON (basin_id) id FROM predictions WHERE owner_user_id = :o ORDER BY basin_id, created_at DESC"
        ).bindparams(o=owner_id)
    ).all()
    preds = db.scalars(select(Prediction).where(Prediction.id.in_(rows))).all() if rows else []
    return {p.basin_id: p for p in preds}


def live_values(sensors: dict[str, Sensor]) -> dict:
    return {m: (s.last_value if s else None) for m, s in ((m, sensors.get(m)) for m in ("do", "temp", "ph"))}


def basin_json(b: Basin, sensors: dict[str, Sensor], th: Thresholds, pred: Prediction | None, with_finance: bool = False) -> dict:
    live = live_values(sensors)
    sat = do_saturation_pct(live["do"], live["temp"]) if live["do"] is not None and live["temp"] is not None else None
    out = {
        "id": str(b.id),
        "name": b.name,
        "species": b.species,
        "species_name": SPECIES_NAMES[b.species],
        "status": b.status,
        "live": live,
        "cls": {m: value_class(th, m, live[m]) for m in live},
        "sat": round(sat, 1) if sat is not None else None,
        "capacity": b.capacity,
        "fish": b.fish_count,
        "density": round(b.fish_count / b.capacity, 1),
        "risk": round(pred.probability, 3) if pred else None,
        "thr": th.as_dict(),
        "sensors": {m: {"id": str(s.id), "code": s.code, "health": s.health} for m, s in sensors.items()},
    }
    if with_finance:
        out["finance"] = finance_json(b)
    return out


def finance_json(b: Basin) -> dict:
    costs = b.feeding_cost + b.maintenance_cost + b.operational_cost
    return {
        "revenue": b.revenue,
        "feed": b.feeding_cost,
        "maint": b.maintenance_cost,
        "ops": b.operational_cost,
        "costs": costs,
        "profit": b.revenue - costs,
    }


def live_basins(db: Session, owner_id: uuid.UUID, with_finance: bool = False) -> list[dict]:
    th = load_thresholds(db)
    preds = latest_predictions(db, owner_id)
    return [basin_json(b, s, th[b.species], preds.get(b.id), with_finance) for b, s in basins_with_sensors(db, owner_id)]


def alert_json(a: Alert, basins: dict[uuid.UUID, Basin], names: dict[uuid.UUID, str]) -> dict:
    b = basins.get(a.basin_id)
    metric = TYPE_TO_METRIC.get(a.metric, a.metric)
    return {
        "id": str(a.id),
        "basin_id": str(a.basin_id),
        "basin": b.name if b else "",
        "species_name": SPECIES_NAMES.get(b.species, "") if b else "",
        "metric": metric,
        "metric_label": METRIC_INFO.get(metric, {}).get("label", a.metric),
        "kind": a.kind,
        "type": a.type,
        "title": a.title,
        "text": a.description,
        "severity": a.severity,
        "value": a.value,
        "time": a.created_at.isoformat(),
        "resolved": a.is_resolved,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "by": names.get(a.resolved_by) if a.resolved_by else None,
        "note": a.resolution_note,
    }


def alerts_for(
    db: Session,
    owner_id: uuid.UUID,
    *,
    kind: str | None = None,
    resolved: bool | None = None,
    basin_id: uuid.UUID | None = None,
    limit: int = 200,
) -> list[dict]:
    q = select(Alert).where(Alert.owner_user_id == owner_id)
    if kind:
        q = q.where(Alert.kind == kind)
    if resolved is not None:
        q = q.where(Alert.is_resolved.is_(resolved))
    if basin_id:
        q = q.where(Alert.basin_id == basin_id)
    rows = db.scalars(q.order_by(Alert.created_at.desc()).limit(limit)).all()
    basins = {b.id: b for b in db.scalars(select(Basin).where(Basin.owner_user_id == owner_id))}
    ids = {a.resolved_by for a in rows if a.resolved_by}
    names = {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    out = [alert_json(a, basins, names) for a in rows]
    if resolved:
        out.sort(key=lambda x: x["resolved_at"] or "", reverse=True)
    else:
        # open alerts: most severe first, then newest
        out.sort(key=lambda x: (x["resolved"], -SEV_RANK[x["severity"]], _neg_time(x["time"])))
    return out


def _neg_time(iso: str) -> float:
    return -datetime.fromisoformat(iso).timestamp()


def role_alert_kind(role: str) -> str | None:
    """Owners see every alert; workers see water alerts; technicians see hardware (sensor) alerts."""
    return None if role == "owner" else "sensor" if role == "technician" else "water"


def series_24h(db: Session, sensor: Sensor, now: datetime | None = None, hours: int = 24) -> dict:
    """15-minute averages for the last 24 h, aligned so the last point is 'now' (97 points)."""
    now = now or datetime.now(UTC)
    n = hours * 4 + 1
    start = now - STEP * (n - 1)
    rows = db.execute(
        text(
            "SELECT floor(extract(epoch FROM (recorded_at - :start)) / 900)::int AS k, avg(value) "
            "FROM readings WHERE sensor_id = :s AND recorded_at > :a AND recorded_at <= :now GROUP BY 1"
        ),
        {"start": start, "s": sensor.id, "a": start - STEP / 2, "now": now},
    ).all()
    by = {int(k): float(v) for k, v in rows}
    values: list[float | None] = []
    last = None
    for i in range(n):
        # bucket i covers ]t_i - 7.5 min, t_i + 7.5 min]: use the nearest bucket index
        v = by.get(i, by.get(i - 1) if i == n - 1 else None)
        if v is None:
            v = last
        values.append(round(v, 3) if v is not None else None)
        last = v if v is not None else last
    first = next((v for v in values if v is not None), None)
    values = [v if v is not None else first for v in values]
    if sensor.last_value is not None:
        values[-1] = round(sensor.last_value, 3)
    times = [(start + STEP * i).isoformat() for i in range(n)]
    return {"times": times, "values": values}


def overnight_low(series: dict) -> dict | None:
    vals = series["values"]
    if not vals or vals[0] is None:
        return None
    i = min(range(len(vals)), key=lambda k: vals[k])
    return {"value": vals[i], "time": series["times"][i], "index": i}
