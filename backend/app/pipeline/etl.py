"""ETL: extract the raw simulator batch -> validate and clean with pandas -> load into `readings`.

Every rejected row is counted by reason, and the counts are logged in `etl_runs`.
Loading inserts row by row through the SQL trigger, which is the alert engine.
"""

import uuid
from collections import Counter
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import notify
from ..models import EtlRun

# physically possible ranges (anything outside is a broken message, not water)
PHYSICAL = {"temp": (-5.0, 45.0), "ph": (0.0, 14.0), "do": (0.0, 25.0)}


def clean(raw: list[dict], known_sensors: set[uuid.UUID]) -> tuple[pd.DataFrame, Counter]:
    """Pure function (unit-tested): returns the clean frame and the rejection counts."""
    reasons: Counter = Counter()
    df = pd.DataFrame(raw, columns=["sensor_id", "owner_id", "metric", "value", "recorded_at"])
    if df.empty:
        return df, reasons

    unknown = ~df["sensor_id"].isin(known_sensors)
    reasons["unknown_sensor"] += int(unknown.sum())
    df = df[~unknown]

    missing = df["value"].isna()
    reasons["missing"] += int(missing.sum())
    df = df[~missing].copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    not_number = df["value"].isna()
    reasons["not_a_number"] += int(not_number.sum())
    df = df[~not_number]

    lo = df["metric"].map(lambda m: PHYSICAL[m][0])
    hi = df["metric"].map(lambda m: PHYSICAL[m][1])
    impossible = (df["value"] < lo) | (df["value"] > hi)
    reasons["impossible"] += int(impossible.sum())
    df = df[~impossible]

    dup = df.duplicated(subset=["sensor_id", "recorded_at"], keep="first")
    reasons["duplicate"] += int(dup.sum())
    df = df[~dup].copy()

    df["value"] = df["value"].round(3)
    return df, +reasons


def load(db: Session, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    db.execute(
        text("INSERT INTO readings (owner_user_id, sensor_id, value, recorded_at) VALUES (:o, :s, :v, :t)"),
        [{"o": r.owner_id, "s": r.sensor_id, "v": float(r.value), "t": r.recorded_at} for r in df.itertuples(index=False)],
    )
    for owner in df["owner_id"].unique():
        notify(db, {"type": "readings", "owner_id": str(owner), "at": datetime.now(UTC).isoformat()})
    return len(df)


class EtlLog:
    """Accumulates accept/reject counts and writes one `etl_runs` row per flush (about once a minute)."""

    def __init__(self) -> None:
        self.received = self.accepted = 0
        self.reasons: Counter = Counter()

    def add(self, received: int, accepted: int, reasons: Counter) -> None:
        self.received += received
        self.accepted += accepted
        self.reasons.update(reasons)

    def flush(self, db: Session, source: str = "simulator") -> None:
        if not self.received:
            return
        db.add(
            EtlRun(
                source=source,
                received=self.received,
                accepted=self.accepted,
                rejected=self.received - self.accepted,
                reasons=dict(self.reasons),
            )
        )
        db.flush()
        self.received = self.accepted = 0
        self.reasons = Counter()
