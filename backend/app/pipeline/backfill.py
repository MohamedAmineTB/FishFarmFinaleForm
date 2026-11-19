"""Historical backfill: generates N days of readings for a farm and bulk-loads them with COPY.

The alert trigger is switched off for the load (`app.bulk_load = on`), so 30 days of
history do not open thousands of alerts. Last values, hourly stats and basin statuses
are rebuilt right after.
"""

import uuid
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import Basin, Owner, Sensor
from .aggregate import aggregate_hourly
from .model import NOISE_SD, TYPE_OF, apply_fault, expected, local_hours

METRIC_OF_TYPE = {v: k for k, v in TYPE_OF.items()}


def backfill_owner(db: Session, owner_id: uuid.UUID, *, days: int = 30, step_minutes: int = 5,
                   end: datetime | None = None, seed: int = 20261118) -> int:
    owner = db.get(Owner, owner_id)
    tz = owner.timezone if owner else "Europe/Paris"
    end = (end or datetime.now(UTC)).replace(microsecond=0)
    n = days * 24 * 60 // step_minutes + 1
    times = [end - timedelta(minutes=step_minutes * (n - 1 - i)) for i in range(n)]
    hours, dayno = local_hours(times, tz)
    rng = np.random.default_rng(seed)

    basins = db.scalars(select(Basin).where(Basin.owner_user_id == owner_id).order_by(Basin.position)).all()
    rows: list[tuple] = []
    last: dict[uuid.UUID, float] = {}
    for b in basins:
        sensors = db.scalars(select(Sensor).where(Sensor.basin_id == b.id)).all()
        for s in sensors:
            m = METRIC_OF_TYPE[s.type]
            vals = expected(b.sim_profile, m, hours, dayno, str(b.id)) + rng.normal(0, NOISE_SD[m], n)
            vals = apply_fault(vals, times, s.sim_fault)
            vals = np.round(vals, 3)
            last[s.id] = float(vals[-1])
            rows.extend((owner_id, s.id, float(v), t) for v, t in zip(vals, times, strict=True))

    db.execute(text("SET LOCAL app.bulk_load = 'on'"))
    raw = db.connection().connection.driver_connection
    with raw.cursor() as cur, cur.copy("COPY readings (owner_user_id, sensor_id, value, recorded_at) FROM STDIN") as cp:
        for r in rows:
            cp.write_row(r)
    db.execute(text("SET LOCAL app.bulk_load = 'off'"))

    for sid, v in last.items():
        db.execute(text("UPDATE sensors SET last_value = :v, last_reading_at = :t WHERE id = :id"),
                   {"v": v, "t": end, "id": sid})
    aggregate_hourly(db, owner_id=owner_id, since=times[0])
    for b in basins:
        db.execute(text("SELECT ff_refresh_basin_status(:b)"), {"b": b.id})
    return len(rows)
