"""Sensor-health job (pandas): tells a broken probe apart from a real water problem.

For each probe it looks at rolling statistics:
- stuck   : the trailing readings are all identical for at least 1 hour (real water always moves)
- spiky   : several sudden jumps much larger than the probe's usual step-to-step change
- drift   : the last 6 hourly means sit consistently above/below the probe's own 7-day baseline
- offline : no reading for 10 minutes while the simulator is running
Stuck and offline probes open a "sensor" alert routed to the technician.
"""

import math
import uuid
from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..db import notify
from ..models import Alert, Basin, Sensor, SimulatorState

LABEL = {"temperature": "Temperature", "ph": "pH", "oxygen": "Oxygen"}
UNIT = {"temperature": " °C", "ph": "", "oxygen": " mg/L"}
DEC = {"temperature": 1, "ph": 2, "oxygen": 2}
DRIFT_LIMIT = {"temperature": 0.5, "ph": 0.1, "oxygen": 0.5}
MIN_JUMP = {"temperature": 0.6, "ph": 0.25, "oxygen": 0.8}


def _duration(td: timedelta) -> str:
    mins = int(round(td.total_seconds() / 60 / 5) * 5)
    h, m = divmod(mins, 60)
    return f"{h} h {m} min" if h and m else f"{h} h" if h else f"{m} min"


def classify(df: pd.DataFrame, baseline: pd.Series | None, sensor_type: str, now: datetime) -> tuple[str, str, dict]:
    """Pure function (unit-tested): df has columns recorded_at, value (last 24 h, sorted)."""
    if df.empty:
        return "offline", "No readings in the last 24 h", {}
    v = df["value"].to_numpy()
    t = df["recorded_at"]
    # stuck: length of the trailing run of identical values
    i = len(v) - 1
    while i > 0 and abs(v[i - 1] - v[-1]) < 1e-6:
        i -= 1
    run = t.iloc[-1] - t.iloc[i] if i < len(v) - 1 else timedelta(0)
    if len(v) - i >= 6 and run >= timedelta(hours=1):
        return "stuck", f"Flat {v[-1]:.{DEC[sensor_type]}f}{UNIT[sensor_type]} for {_duration(now - t.iloc[i])}", {
            "flat_since": t.iloc[i].isoformat(), "value": float(v[-1])}
    # spiky: big jumps in the last 2 h
    recent = df[df["recorded_at"] >= now - timedelta(hours=2)]["value"].diff().abs().dropna()
    if len(recent) > 10:
        mad = float((recent - recent.median()).abs().median()) or 1e-6
        jumps = int((recent > max(8 * mad, MIN_JUMP[sensor_type])).sum())
        if jumps >= 3:
            return "spiky", f"{jumps} sudden jumps in the last 2 h", {"jumps": jumps}
    # drift: compare the last 6 hourly means with the same hours of the previous days
    if baseline is not None and not baseline.empty:
        last6 = df[df["recorded_at"] >= now - timedelta(hours=6)].copy()
        if len(last6) > 5:
            last6["h"] = last6["recorded_at"].dt.hour
            hourly = last6.groupby("h")["value"].mean()
            common = hourly.index.intersection(baseline.index)
            if len(common) >= 4:
                resid = hourly[common] - baseline[common]
                off = float(resid.mean())
                same_sign = bool((resid > 0).all() or (resid < 0).all())
                if abs(off) >= DRIFT_LIMIT[sensor_type] and same_sign:
                    return "drift", f"{off:+.{DEC[sensor_type]}f} vs. its 7-day baseline, calibration due", {"offset": off}
    return "ok", "Readings vary normally", {}


def run_health(db: Session, owner_id: uuid.UUID | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    q = select(Sensor)
    if owner_id:
        q = q.where(Sensor.owner_user_id == owner_id)
    sensors = db.scalars(q).all()
    paused = {s.owner_user_id: s.paused for s in db.scalars(select(SimulatorState)).all()}
    counts: dict[str, int] = {}
    for s in sensors:
        rows = db.execute(text("SELECT recorded_at, value FROM readings WHERE sensor_id = :s AND recorded_at > :a "
                               "ORDER BY recorded_at"), {"s": s.id, "a": now - timedelta(hours=24)}).all()
        df = pd.DataFrame(rows, columns=["recorded_at", "value"])
        if not df.empty:
            df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
        base_rows = db.execute(text(
            "SELECT extract(hour FROM hour AT TIME ZONE 'UTC')::int AS h, avg(mean_value) FROM hourly_stats WHERE sensor_id = :s "
            "AND hour BETWEEN :a AND :b GROUP BY 1"), {"s": s.id, "a": now - timedelta(days=8),
                                                      "b": now - timedelta(days=1)}).all()
        baseline = pd.Series({int(h): float(m) for h, m in base_rows}) if base_rows else None
        # hourly_stats hours are UTC; the readings frame is UTC too, so the hours line up
        health, note, evidence = classify(df, baseline, s.type, now)
        if (health == "ok" and s.last_reading_at and now - s.last_reading_at > timedelta(minutes=10)
                and not paused.get(s.owner_user_id, False)):
            health, note = "offline", f"No reading for {_duration(now - s.last_reading_at)}"
        counts[health] = counts.get(health, 0) + 1
        changed = (s.health, s.health_note) != (health, note)
        s.health, s.health_note = health, note
        if health in ("stuck", "offline"):
            _open_sensor_alert(db, s, health, note, evidence, now)
        if changed:
            notify(db, {"type": "sensor_health", "owner_id": str(s.owner_user_id), "sensor_id": str(s.id),
                        "health": health})
    db.flush()
    return counts


def _open_sensor_alert(db: Session, s: Sensor, health: str, note: str, evidence: dict, now: datetime) -> None:
    exists = db.scalar(select(Alert.id).where(Alert.sensor_id == s.id, Alert.kind == "sensor",
                                              Alert.is_resolved.is_(False)))
    if exists:
        return
    basin = db.get(Basin, s.basin_id)
    if health == "stuck":
        since = datetime.fromisoformat(evidence["flat_since"])
        # how much did the same metric move in the other basins over the same period?
        moves = db.execute(text(
            "SELECT max(r.value) - min(r.value) FROM readings r JOIN sensors o ON o.id = r.sensor_id "
            "WHERE o.owner_user_id = :own AND o.type = :t AND o.id <> :s AND r.recorded_at >= :a GROUP BY o.id"),
            {"own": s.owner_user_id, "t": s.type, "s": s.id, "a": since}).scalars().all()
        hrs = int((now - since).total_seconds() // 3600)
        dur = f"over {hrs} h" if hrs >= 1 else f"{int((now - since).total_seconds() // 60)} min"
        unit = UNIT[s.type].strip()
        if moves:
            lo, hi = min(moves), max(moves)
            if s.type == "temperature":
                lo_r, hi_r = math.floor(lo), max(math.ceil(hi), math.floor(lo) + 1)
                mv = f"{lo_r}–{hi_r} {unit}".strip()
            else:
                mv = f"{lo:.2f}–{hi:.2f} {unit}".strip()
            descr = (f"Reads exactly {evidence['value']:.{DEC[s.type]}f}{UNIT[s.type]} for {dur} while other basins "
                     f"moved {mv}.")
        else:
            descr = f"Reads exactly {evidence['value']:.{DEC[s.type]}f}{UNIT[s.type]} for {dur}."
        title, created, value = f"{LABEL[s.type]} probe not changing", since, evidence["value"]
    else:
        title, descr, created, value = f"{LABEL[s.type]} probe offline", note + ".", now, None
    a = Alert(owner_user_id=s.owner_user_id, basin_id=s.basin_id, sensor_id=s.id, kind="sensor",
              metric=s.type, type=health, title=title, description=descr, severity="low", value=value,
              created_at=created)
    db.add(a)
    db.flush()
    notify(db, {"type": "alert", "action": "created", "owner_id": str(s.owner_user_id), "alert_id": str(a.id),
                "basin_id": str(s.basin_id), "kind": "sensor", "title": title, "severity": "low",
                "basin_name": basin.name if basin else ""})
