"""Feature engineering for the oxygen-drop model.

One sample = one basin at one moment t. Features describe the water up to t; the label says
whether dissolved oxygen falls below the species warning level between t and the next 06:00
(the pre-dawn low), i.e. "will oxygen drop tonight?".
"""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

FEATURES = [
    "do_now",
    "do_decline_3h",
    "do_mean_6h",
    "do_std_6h",
    "do_min_24h_gap",
    "do_gap",
    "temp_now",
    "ph_now",
    "hour_sin",
    "hour_cos",
    "feed_kg_per_m3",
]
# what the UI shows as "top features" (label, unit, feature column)
DISPLAY = [
    ("Evening oxygen decline", "mg/L per h", "do_decline_3h"),
    ("Water temperature", "°C", "temp_now"),
    ("Evening feed", "kg", "feed_kg"),
]
FEED_KG_PER_FISH = 0.012  # evening ration used by the demo farm (kg per fish)

SERIES_SQL = """
SELECT s.basin_id, s.type::text AS metric,
       to_timestamp(floor(extract(epoch FROM r.recorded_at) / 900) * 900) AS t, avg(r.value) AS v
FROM readings r JOIN sensors s ON s.id = r.sensor_id
WHERE s.basin_id = ANY(:basins) AND r.recorded_at >= :since
GROUP BY 1, 2, 3
"""


def load_series(db: Session, basin_ids: list[uuid.UUID], since: datetime) -> dict[uuid.UUID, pd.DataFrame]:
    """15-minute means per basin, one column per metric (do, temp, ph), regular index."""
    rows = db.execute(text(SERIES_SQL), {"basins": list(basin_ids), "since": since}).all()
    df = pd.DataFrame(rows, columns=["basin_id", "metric", "t", "v"])
    out: dict[uuid.UUID, pd.DataFrame] = {}
    if df.empty:
        return out
    df["t"] = pd.to_datetime(df["t"], utc=True)
    df["metric"] = df["metric"].map({"oxygen": "do", "temperature": "temp", "ph": "ph"})
    for bid, g in df.groupby("basin_id"):
        p = g.pivot_table(index="t", columns="metric", values="v").sort_index()
        p = p.asfreq("15min").interpolate(limit=8)
        out[bid] = p
    return out


def compute_features(series: pd.DataFrame, *, fish: int, capacity: float, warn: float, tz: str) -> pd.DataFrame:
    """Feature frame indexed like `series` (rolling windows look only at the past)."""
    s = series
    f = pd.DataFrame(index=s.index)
    f["do_now"] = s["do"]
    f["do_decline_3h"] = (s["do"].shift(12) - s["do"]) / 3.0  # positive = oxygen falling (mg/L per hour)
    f["do_mean_6h"] = s["do"].rolling(24, min_periods=12).mean()
    f["do_std_6h"] = s["do"].rolling(24, min_periods=12).std()
    f["do_min_24h_gap"] = s["do"].rolling(96, min_periods=48).min() - warn
    f["do_gap"] = s["do"] - warn
    f["temp_now"] = s.get("temp")
    f["ph_now"] = s.get("ph")
    local = s.index.tz_convert(ZoneInfo(tz))
    hours = local.hour + local.minute / 60
    f["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    f["hour_cos"] = np.cos(2 * np.pi * hours / 24)
    f["feed_kg"] = fish * FEED_KG_PER_FISH
    f["feed_kg_per_m3"] = f["feed_kg"] / capacity
    return f


def labels(series: pd.DataFrame, *, warn: float, tz: str) -> pd.Series:
    """1 if oxygen goes below `warn` between t and the next 06:00 local time, NaN if that window is incomplete."""
    zi = ZoneInfo(tz)
    do = series["do"]
    end_data = do.index[-1]
    out = pd.Series(np.nan, index=do.index)
    values = do.to_numpy()
    idx = do.index
    for i, t in enumerate(idx):
        lt = t.tz_convert(zi)
        six = lt.replace(hour=6, minute=0, second=0, microsecond=0)
        if lt >= six:
            six = six + timedelta(days=1)
        end = six.tz_convert("UTC")
        if end > end_data:
            break
        j = idx.searchsorted(end, side="right")
        window = values[i + 1 : j]
        if len(window) == 0 or np.isnan(window).all():
            continue
        out.iloc[i] = float(np.nanmin(window) < warn)
    return out
