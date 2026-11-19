"""Water model used by the backfill and the live simulator.

Each basin has a profile: a base value and a daily amplitude per metric. Values follow a
day-night cosine (oxygen peaks mid-afternoon when algae photosynthesise, lowest just
before dawn), vary a little from day to day, and get random noise. Sensor faults
(stuck / drift) are applied on top so the sensor-health job has something to find.
"""

import hashlib
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

METRICS = ("temp", "ph", "do")  # sensor order in a basin: temperature, pH, oxygen
TYPE_OF = {"temp": "temperature", "ph": "ph", "do": "oxygen"}
PEAK_HOUR = {"do": 15.5, "temp": 16.0, "ph": 16.0}
NOISE_SD = {"do": 0.12, "temp": 0.08, "ph": 0.03}

DEFAULT_PROFILES = {
    "tilapia": {"base": {"temp": 28.0, "do": 7.0, "ph": 7.4}, "amp": {"temp": 0.8, "do": 1.4, "ph": 0.25}},
    "rainbow_trout": {"base": {"temp": 15.0, "do": 9.0, "ph": 7.4}, "amp": {"temp": 0.6, "do": 1.2, "ph": 0.2}},
    "common_carp": {"base": {"temp": 25.0, "do": 7.0, "ph": 7.6}, "amp": {"temp": 0.9, "do": 1.4, "ph": 0.25}},
    "sea_bass": {"base": {"temp": 20.0, "do": 7.6, "ph": 7.9}, "amp": {"temp": 0.6, "do": 1.0, "ph": 0.15}},
    "sea_bream": {"base": {"temp": 21.0, "do": 7.5, "ph": 8.0}, "amp": {"temp": 0.6, "do": 1.0, "ph": 0.15}},
    "atlantic_salmon": {"base": {"temp": 12.0, "do": 9.6, "ph": 7.3}, "amp": {"temp": 0.5, "do": 1.0, "ph": 0.15}},
}


def default_profile(species: str) -> dict:
    p = DEFAULT_PROFILES.get(species, DEFAULT_PROFILES["tilapia"])
    return {"base": dict(p["base"]), "amp": dict(p["amp"])}


def _day_factors(seed_key: str, day_ordinal: int) -> tuple[float, float]:
    """Deterministic per-basin, per-day variation: (amplitude scale, oxygen base shift)."""
    h = hashlib.sha256(f"{seed_key}:{day_ordinal}".encode()).digest()
    a = 0.88 + 0.24 * (h[0] / 255)  # 0.88 .. 1.12
    s = -0.2 + 0.4 * (h[1] / 255)  # -0.20 .. +0.20 mg/L
    return a, s


def local_hours(ts: np.ndarray | list[datetime], tz: str) -> tuple[np.ndarray, np.ndarray]:
    """Local hour of day (float) and local day ordinal for each UTC timestamp."""
    zi = ZoneInfo(tz)
    hours, days = [], []
    for t in ts:
        lt = t.astimezone(zi)
        hours.append(lt.hour + lt.minute / 60 + lt.second / 3600)
        days.append(lt.toordinal())
    return np.array(hours), np.array(days)


def expected(profile: dict, metric: str, hours: np.ndarray, days: np.ndarray, seed_key: str) -> np.ndarray:
    """Noise-free value of a metric at the given local hours (vectorised)."""
    base = profile["base"][metric]
    amp = profile["amp"][metric]
    out = np.empty(len(hours))
    cache: dict[int, tuple[float, float]] = {}
    for i, (h, d) in enumerate(zip(hours, days, strict=True)):
        if d not in cache:
            cache[d] = _day_factors(seed_key, int(d))
        a, s = cache[d]
        v = base + amp * a * math.cos(2 * math.pi * (h - PEAK_HOUR[metric]) / 24)
        if metric == "do":
            v += s
            dip = profile.get("night_dip")
            # an extra pre-dawn oxygen dip (e.g. trout basin with a heavy evening feed)
            if dip and dip["from"] < h < dip["to"]:
                v -= dip["depth"] * a * math.sin(math.pi * (h - dip["from"]) / (dip["to"] - dip["from"]))
        out[i] = v
    return out


def apply_fault(values: np.ndarray, times: list[datetime], fault: dict | None) -> np.ndarray:
    """Sensor faults: 'stuck' (flat value since a time) or 'drift' (offset growing since a time)."""
    if not fault:
        return values
    since = datetime.fromisoformat(fault["since"])
    out = values.copy()
    for i, t in enumerate(times):
        if t < since:
            continue
        if fault["type"] == "stuck":
            out[i] = fault["value"]
        elif fault["type"] == "drift":
            hrs = (t - since).total_seconds() / 3600
            out[i] += min(fault["max"], fault["rate_per_h"] * hrs)
    return out
