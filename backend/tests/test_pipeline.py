"""Data pipeline: simulator, pandas cleaning, sensor-health classification, aggregation, realtime events."""

import uuid
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.db import session_scope
from app.pipeline.etl import EtlLog, clean, load
from app.pipeline.health import classify
from app.pipeline.model import default_profile, expected, local_hours
from app.pipeline.runner import load_world
from app.pipeline.simulator import SimBasin, SimSensor, Simulator


def _raw(sid, owner, metric, value, t):
    return {"sensor_id": sid, "owner_id": owner, "metric": metric, "value": value, "recorded_at": t}


def test_clean_rejects_dirty_rows():
    a, b, owner = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    t = datetime.now(UTC)
    raw = [
        _raw(a, owner, "do", 7.1234, t),
        _raw(a, owner, "do", 7.1234, t),  # duplicate
        _raw(b, owner, "ph", None, t),  # missing
        _raw(b, owner, "ph", 15.2, t + timedelta(seconds=1)),  # impossible pH
        _raw(b, owner, "temp", -40, t + timedelta(seconds=2)),  # impossible temperature
        _raw(uuid.uuid4(), owner, "do", 7.0, t),  # unknown probe
        _raw(b, owner, "ph", 7.4, t + timedelta(seconds=3)),
    ]
    df, reasons = clean(raw, {a, b})
    assert len(df) == 2
    assert dict(reasons) == {"duplicate": 1, "missing": 1, "impossible": 2, "unknown_sensor": 1}
    assert df.iloc[0]["value"] == 7.123


def test_day_night_oxygen_cycle():
    prof = default_profile("tilapia")
    tz = "Europe/Paris"
    day = datetime(2026, 6, 1, tzinfo=UTC)
    times = [day + timedelta(hours=h) for h in range(24)]
    hours, days = local_hours(times, tz)
    v = expected(prof, "do", hours, days, "x")
    # oxygen peaks mid-afternoon and is lowest just before dawn
    assert 13 <= hours[int(np.argmax(v))] <= 18
    assert hours[int(np.argmin(v))] <= 6 or hours[int(np.argmin(v))] >= 23


def test_simulator_spikes_dirty_data_and_faults():
    owner = uuid.uuid4()
    b = SimBasin(id=uuid.uuid4(), owner_id=owner, profile=default_profile("tilapia"), tz="Europe/Paris")
    b.sensors = [SimSensor(id=uuid.uuid4(), owner_id=owner, basin_id=b.id, metric=m, min_value=lo, max_value=hi,
                           fault=None) for m, lo, hi in (("temp", 22, 34), ("ph", 6.5, 8.5), ("do", 5, None))]
    sim = Simulator(spike_prob=1.0, dirty_prob=1.0, fault_prob=1.0, seed=1)
    raw, faults = sim.tick([b], datetime.now(UTC))
    assert len(raw) >= 3
    assert len(faults) == 1 and faults[0][1]["type"] in ("stuck", "drift")
    df, reasons = clean(raw, {s.id for s in b.sensors})
    assert sum(reasons.values()) >= 1  # the dirty row was caught
    # a quiet simulator returns exactly one clean reading per probe
    quiet = Simulator(0, 0, 0, seed=2)
    raw, faults = quiet.tick([b], datetime.now(UTC))
    df, reasons = clean(raw, {s.id for s in b.sensors})
    assert len(df) == 3 and not reasons and not faults


def _frame(values, end, step_min=5):
    n = len(values)
    times = [end - timedelta(minutes=step_min * (n - 1 - i)) for i in range(n)]
    return pd.DataFrame({"recorded_at": pd.to_datetime(times, utc=True), "value": values})


def test_health_classifier():
    now = datetime.now(UTC)
    rng = np.random.default_rng(0)
    normal = 7 + np.sin(np.linspace(0, 6, 288)) + rng.normal(0, 0.05, 288)
    assert classify(_frame(normal, now), None, "oxygen", now)[0] == "ok"
    stuck = normal.copy()
    stuck[-40:] = 26.0  # 3 h 15 min flat at 5-minute steps
    h, note, _ = classify(_frame(stuck, now), None, "temperature", now)
    assert h == "stuck" and note == "Flat 26.0 °C for 3 h 15 min"
    spiky = normal.copy()
    spiky[-20::4] += 3
    assert classify(_frame(spiky, now), None, "oxygen", now)[0] == "spiky"
    df = _frame(np.full(288, 7.5) + rng.normal(0, 0.01, 288), now)
    baseline = pd.Series({h: 7.3 for h in range(24)})
    h, note, ev = classify(df, baseline, "ph", now)
    assert h == "drift" and note.startswith("+0.20")


def test_etl_load_runs_trigger_and_logs(client):
    with session_scope() as db:
        world = [b for b in load_world(db) if b.sensors]
        sensor = world[0].sensors[0]
        before = db.execute(text("SELECT count(*) FROM readings WHERE sensor_id = :s"), {"s": sensor.id}).scalar()
        raw = [_raw(sensor.id, sensor.owner_id, sensor.metric, 7.0 if sensor.metric != "temp" else 25.0,
                    datetime.now(UTC)), _raw(sensor.id, sensor.owner_id, sensor.metric, None, datetime.now(UTC))]
        df, reasons = clean(raw, {sensor.id})
        assert load(db, df) == 1
        log = EtlLog()
        log.add(len(raw), len(df), reasons)
        log.flush(db)
        after = db.execute(text("SELECT count(*) FROM readings WHERE sensor_id = :s"), {"s": sensor.id}).scalar()
        assert after == before + 1
        assert db.execute(text("SELECT rejected FROM etl_runs ORDER BY id DESC LIMIT 1")).scalar() == 1


def test_hourly_aggregation_exists(client):
    with session_scope() as db:
        n = db.execute(text("SELECT count(*) FROM hourly_stats")).scalar()
        assert n > 12 * 24 * 29  # 30 days of hourly stats for 12 probes


def test_websocket_receives_farm_events_only(client, owner_h, other_owner_h):
    token = owner_h["Authorization"][7:]
    with client.websocket_connect(f"/ws?token={token}") as ws:
        # an event for another farm must not arrive; one for this farm must
        client.post("/api/simulator/pause", headers=other_owner_h)
        client.post("/api/simulator/pause", headers=owner_h)
        event = ws.receive_json()
        assert event["type"] == "simulator" and event["paused"] is True
        client.post("/api/simulator/resume", headers=owner_h)
        assert ws.receive_json()["paused"] is False
    client.post("/api/simulator/resume", headers=other_owner_h)


def test_websocket_rejects_bad_token(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws?token=bad") as ws:
        ws.receive_json()
