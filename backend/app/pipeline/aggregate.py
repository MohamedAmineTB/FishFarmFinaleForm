"""Batch aggregation job: hourly min / max / mean per sensor, upserted into `hourly_stats`."""

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

AGG_SQL = """
INSERT INTO hourly_stats (sensor_id, hour, owner_user_id, basin_id, metric, min_value, max_value, mean_value, n)
SELECT r.sensor_id, date_trunc('hour', r.recorded_at) AS hour, s.owner_user_id, s.basin_id, s.type,
       min(r.value), max(r.value), avg(r.value), count(*)
FROM readings r JOIN sensors s ON s.id = r.sensor_id
WHERE r.recorded_at >= date_trunc('hour', CAST(:since AS timestamptz)) {owner_filter}
GROUP BY r.sensor_id, date_trunc('hour', r.recorded_at), s.owner_user_id, s.basin_id, s.type
ON CONFLICT (sensor_id, hour) DO UPDATE SET
  min_value = EXCLUDED.min_value, max_value = EXCLUDED.max_value,
  mean_value = EXCLUDED.mean_value, n = EXCLUDED.n
"""


def aggregate_hourly(db: Session, since: datetime, owner_id: uuid.UUID | None = None) -> int:
    sql = AGG_SQL.format(owner_filter="AND s.owner_user_id = :owner" if owner_id else "")
    params = {"since": since}
    if owner_id:
        params["owner"] = owner_id
    return db.execute(text(sql), params).rowcount
