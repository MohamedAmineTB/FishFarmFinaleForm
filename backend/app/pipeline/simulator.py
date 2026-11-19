"""Sensor simulator: produces one raw reading per probe every tick (6 s), like real probes would.

The raw batch is deliberately imperfect so the ETL has work to do:
- spikes      : with SIM_SPIKE_PROB per tick, one out-of-range oxygen or pH reading (triggers an alert)
- dirty data  : with SIM_DIRTY_PROB per tick, a missing value, an impossible value or a duplicate row
- probe faults: with SIM_FAULT_PROB per tick, a probe gets stuck or starts drifting (found by the health job)
"""

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from .model import NOISE_SD, apply_fault, expected, local_hours

IMPOSSIBLE = {"temp": 99.0, "ph": 15.2, "do": -3.0}


@dataclass
class SimSensor:
    id: uuid.UUID
    owner_id: uuid.UUID
    basin_id: uuid.UUID
    metric: str
    min_value: float | None
    max_value: float | None
    fault: dict | None
    truth: float | None = None  # the "real" water value, before any probe fault


@dataclass
class SimBasin:
    id: uuid.UUID
    owner_id: uuid.UUID
    profile: dict
    tz: str
    sensors: list[SimSensor] = field(default_factory=list)


class Simulator:
    def __init__(self, spike_prob: float, dirty_prob: float, fault_prob: float, seed: int | None = None):
        self.spike_prob, self.dirty_prob, self.fault_prob = spike_prob, dirty_prob, fault_prob
        self.rng = random.Random(seed)
        self.np = np.random.default_rng(seed)
        self.truth: dict[uuid.UUID, float] = {}

    def tick(self, basins: list[SimBasin], now: datetime) -> tuple[list[dict], list[tuple[uuid.UUID, dict]]]:
        """Returns (raw records, new probe faults to store)."""
        records: list[dict] = []
        new_faults: list[tuple[uuid.UUID, dict]] = []
        for b in basins:
            hours, days = local_hours([now], b.tz)
            for s in b.sensors:
                target = float(expected(b.profile, s.metric, hours, days, str(b.id))[0])
                prev = self.truth.get(s.id, s.truth if s.truth is not None else target)
                # mean-reverting random walk around the day-night curve
                v = prev + (target - prev) * 0.08 + self.np.normal(0, NOISE_SD[s.metric] * 0.5)
                self.truth[s.id] = v
                shown = float(apply_fault(np.array([v]), [now], s.fault)[0])
                records.append({"sensor_id": s.id, "owner_id": s.owner_id, "metric": s.metric,
                                "value": round(shown, 3), "recorded_at": now})

        by_owner: dict[uuid.UUID, list[SimBasin]] = {}
        for b in basins:
            by_owner.setdefault(b.owner_id, []).append(b)
        for owner_basins in by_owner.values():
            sensors = [s for b in owner_basins for s in b.sensors]
            if not sensors:
                continue
            # 1) an out-of-range spike (one reading, the water itself is unchanged)
            if self.rng.random() < self.spike_prob:
                cands = [s for s in sensors if s.metric in ("do", "ph") and not s.fault]
                if cands:
                    s = self.rng.choice(cands)
                    if s.metric == "ph" and s.max_value is not None:
                        val = s.max_value + self.rng.uniform(0.05, 0.3)
                    elif s.metric == "do" and s.min_value is not None:
                        val = s.min_value - self.rng.uniform(0.1, 0.6)
                    else:
                        val = None
                    if val is not None:
                        for r in records:
                            if r["sensor_id"] == s.id:
                                r["value"] = round(val, 3)
            # 2) dirty data for the ETL to clean
            if self.rng.random() < self.dirty_prob:
                s = self.rng.choice(sensors)
                kind = self.rng.choice(["missing", "impossible", "duplicate"])
                base = {"sensor_id": s.id, "owner_id": s.owner_id, "metric": s.metric, "recorded_at": now}
                if kind == "missing":
                    records = [r for r in records if r["sensor_id"] != s.id] + [{**base, "value": None}]
                elif kind == "impossible":
                    records.append({**base, "value": IMPOSSIBLE[s.metric], "recorded_at": now + timedelta(milliseconds=1)})
                else:
                    original = next(r for r in records if r["sensor_id"] == s.id)
                    records.append(dict(original))
            # 3) occasionally a probe develops a fault
            if self.rng.random() < self.fault_prob:
                healthy = [s for s in sensors if not s.fault]
                if healthy:
                    s = self.rng.choice(healthy)
                    if self.rng.random() < 0.5:
                        fault = {"type": "stuck", "value": round(self.truth.get(s.id, 0.0), 1), "since": now.isoformat()}
                    else:
                        rate = {"temp": 0.08, "ph": 0.01, "do": 0.08}[s.metric]
                        fault = {"type": "drift", "rate_per_h": rate, "max": rate * 20, "since": now.isoformat()}
                    s.fault = fault
                    new_faults.append((s.id, fault))
        return records, new_faults
