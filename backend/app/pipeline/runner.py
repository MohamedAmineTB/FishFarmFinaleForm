"""Pipeline service (its own process / container): `python -m app.pipeline.runner`

Schedule:
- every 6 s   : simulator tick -> ETL (clean with pandas) -> load (SQL trigger raises alerts) -> notify
- every 60 s  : sensor-health job, ETL accept/reject log
- every 5 min : hourly aggregation, oxygen-drop predictions
"""

import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from ..config import get_settings
from ..db import session_scope
from ..models import Basin, Owner, Sensor, SimulatorState
from .aggregate import aggregate_hourly
from .etl import EtlLog, clean, load
from .health import run_health
from .model import TYPE_OF
from .simulator import SimBasin, SimSensor, Simulator

log = logging.getLogger("fishfarm.pipeline")
METRIC_OF = {v: k for k, v in TYPE_OF.items()}


def load_world(db) -> list[SimBasin]:
    paused = {s.owner_user_id for s in db.scalars(select(SimulatorState).where(SimulatorState.paused.is_(True)))}
    tz = {o.user_id: o.timezone for o in db.scalars(select(Owner))}
    basins = {
        b.id: SimBasin(id=b.id, owner_id=b.owner_user_id, profile=b.sim_profile, tz=tz.get(b.owner_user_id, "Europe/Paris"))
        for b in db.scalars(select(Basin).where(Basin.status != "inactive"))
        if b.owner_user_id not in paused
    }
    for s in db.scalars(select(Sensor).where(Sensor.status == "active")):
        if s.basin_id in basins:
            basins[s.basin_id].sensors.append(
                SimSensor(
                    id=s.id,
                    owner_id=s.owner_user_id,
                    basin_id=s.basin_id,
                    metric=METRIC_OF[s.type],
                    min_value=s.min_value,
                    max_value=s.max_value,
                    fault=s.sim_fault,
                    truth=None,
                )
            )
    return list(basins.values())


def run_predictions(db) -> None:
    try:
        from ..ml.predict import predict_all
    except ImportError:
        return
    predict_all(db)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = get_settings()
    sim = Simulator(s.sim_spike_prob, s.sim_dirty_prob, s.sim_fault_prob)
    etl_log = EtlLog()
    last = {"health": 0.0, "agg": 0.0, "world": 0.0}
    world: list[SimBasin] = []
    log.info("pipeline started: tick every %.0f s", s.sim_interval_seconds)
    # start the random walk from the last stored values so the curves continue smoothly
    with session_scope() as db:
        for sid, v in db.execute(text("SELECT id, last_value FROM sensors WHERE last_value IS NOT NULL")).all():
            sim.truth[sid] = float(v)

    while True:
        t0 = time.monotonic()
        now = datetime.now(UTC).replace(microsecond=0)
        try:
            with session_scope() as db:
                # reload basins, probes and faults every 10 s (new basins, repairs, pause/resume)
                if t0 - last["world"] > 10 or not world:
                    world = load_world(db)
                    last["world"] = t0
                raw, new_faults = sim.tick(world, now)
                known: set[uuid.UUID] = {sb.id for b in world for sb in b.sensors}
                df, reasons = clean(raw, known)
                n = load(db, df)
                etl_log.add(len(raw), n, reasons)
                for sid, fault in new_faults:
                    db.execute(
                        text("UPDATE sensors SET sim_fault = CAST(:f AS jsonb) WHERE id = :s"), {"f": json.dumps(fault), "s": sid}
                    )
                    log.info("injected probe fault %s on %s", fault["type"], sid)
            if t0 - last["health"] > 60:
                with session_scope() as db:
                    counts = run_health(db, now=now)
                    etl_log.flush(db)
                log.info("health %s", counts)
                last["health"] = t0
            if t0 - last["agg"] > 300:
                with session_scope() as db:
                    aggregate_hourly(db, since=now - timedelta(hours=2))
                    run_predictions(db)
                last["agg"] = t0
        except Exception:
            log.exception("pipeline tick failed")
        time.sleep(max(0.0, s.sim_interval_seconds - (time.monotonic() - t0)))


if __name__ == "__main__":
    main()
