"""Aquaculture domain logic shared by the API, the pipeline, the ML model and the assistant.

Deterministic code owns thresholds and chemistry; nothing here depends on the LLM.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import SpeciesThreshold

SPECIES_NAMES = {
    "tilapia": "Nile tilapia",
    "rainbow_trout": "Rainbow trout",
    "common_carp": "Common carp",
    "sea_bass": "European sea bass",
    "sea_bream": "Gilthead sea bream",
    "atlantic_salmon": "Atlantic salmon",
}
SPECIES_CODES = list(SPECIES_NAMES)

# The API speaks the prototype's short metric keys; the database uses sensor_type names.
METRIC_TO_TYPE = {"do": "oxygen", "temp": "temperature", "ph": "ph"}
TYPE_TO_METRIC = {v: k for k, v in METRIC_TO_TYPE.items()}
METRIC_INFO = {
    "do": {"label": "Dissolved oxygen", "short": "Oxygen", "unit": "mg/L", "dec": 2},
    "temp": {"label": "Water temperature", "short": "Temp", "unit": "°C", "dec": 1},
    "ph": {"label": "pH", "short": "pH", "unit": "", "dec": 2},
}

# FAO freshwater oxygen solubility (mg/L at 1 atm): 10 °C 11.28, 20 °C 9.08, 30 °C 7.54
_SOLUBILITY = [(10.0, 11.28), (20.0, 9.08), (30.0, 7.54)]


def do_solubility(temp_c: float) -> float:
    """Oxygen solubility in fresh water (mg/L), linearly interpolated from the FAO table (clamped 0–40 °C)."""
    t = max(0.0, min(40.0, temp_c))
    a, b = (_SOLUBILITY[0], _SOLUBILITY[1]) if t <= 20 else (_SOLUBILITY[1], _SOLUBILITY[2])
    return a[1] + (b[1] - a[1]) * (t - a[0]) / (b[0] - a[0])


def do_saturation_pct(do_mg_l: float, temp_c: float) -> float:
    """Dissolved oxygen as a percentage of saturation at this temperature."""
    return 100.0 * do_mg_l / do_solubility(temp_c)


def unionized_ammonia_fraction(ph: float, temp_c: float) -> float:
    """Share of total ammonia nitrogen present as toxic un-ionized NH3 (Emerson et al. 1975).

    pKa = 0.09018 + 2729.92 / T(K); fraction = 1 / (10^(pKa - pH) + 1).
    Checks: 24 °C, pH 8 -> 0.0502 ; 24 °C, pH 9 -> 0.3456 (UF/IFAS tables).
    """
    pka = 0.09018 + 2729.92 / (temp_c + 273.15)
    return 1.0 / (10 ** (pka - ph) + 1.0)


NH3_TOXIC_MG_L = 0.05
NITRITE_TOXIC_MG_L = 0.10


@dataclass
class Thresholds:
    species: str
    name: str
    do_warn: float | None
    do_crit: float | None
    do_emergency: float | None
    temp_min: float | None
    temp_max: float | None
    ph_min: float | None
    ph_max: float | None
    sources: dict  # metric -> {label, url, verified, note}

    def as_dict(self) -> dict:
        return {
            "species": self.species, "name": self.name,
            "do": {"warn": self.do_warn, "crit": self.do_crit, "emergency": self.do_emergency},
            "temp": {"min": self.temp_min, "max": self.temp_max},
            "ph": {"min": self.ph_min, "max": self.ph_max},
            "src": self.sources.get("temperature", self.sources.get("oxygen", {})).get("label", ""),
            "sources": self.sources,
        }


def load_thresholds(db: Session) -> dict[str, Thresholds]:
    rows = db.scalars(select(SpeciesThreshold)).all()
    by: dict[str, dict[str, SpeciesThreshold]] = {}
    for r in rows:
        by.setdefault(r.species, {})[r.metric] = r
    out = {}
    for sp in SPECIES_CODES:
        m = by.get(sp, {})
        o, t, p = m.get("oxygen"), m.get("temperature"), m.get("ph")
        out[sp] = Thresholds(
            species=sp, name=SPECIES_NAMES[sp],
            do_warn=o.warning_min if o else None, do_crit=o.critical_min if o else None,
            do_emergency=o.emergency_min if o else None,
            temp_min=t.warning_min if t else None, temp_max=t.warning_max if t else None,
            ph_min=p.warning_min if p else None, ph_max=p.warning_max if p else None,
            sources={k: {"label": v.source_label, "url": v.source_url, "verified": v.verified, "note": v.note}
                     for k, v in m.items()},
        )
    return out


def sensor_range(th: Thresholds, sensor_type: str) -> tuple[float | None, float | None]:
    """Safe range stored on a sensor (used by the SQL alert trigger)."""
    if sensor_type == "oxygen":
        return th.do_warn, None
    if sensor_type == "temperature":
        return th.temp_min, th.temp_max
    return th.ph_min, th.ph_max


def _lt(v, lim):
    return v is not None and lim is not None and v < lim


def _gt(v, lim):
    return v is not None and lim is not None and v > lim


def basin_status(th: Thresholds, live: dict, has_open_non_low_alert: bool) -> str:
    """Python mirror of the SQL function ff_basin_status (DESIGN_SPEC §5)."""
    d, t, p = live.get("do"), live.get("temp"), live.get("ph")
    if _lt(d, th.do_crit) or (th.temp_max is not None and _gt(t, th.temp_max + 2)):
        return "critical"
    if _lt(d, th.do_warn) or _gt(p, th.ph_max) or _lt(p, th.ph_min) or _gt(t, th.temp_max) or _lt(t, th.temp_min):
        return "warning"
    return "warning" if has_open_non_low_alert else "healthy"


def value_class(th: Thresholds, metric: str, v: float | None) -> str:
    """'bad' / 'meh' / '' like the prototype's cls(): colours a live value."""
    if v is None:
        return ""
    if metric == "do":
        return "bad" if _lt(v, th.do_crit) else "meh" if _lt(v, th.do_warn) else ""
    if metric == "ph":
        return "meh" if (_gt(v, th.ph_max) or _lt(v, th.ph_min)) else ""
    return "meh" if (_gt(v, th.temp_max) or _lt(v, th.temp_min)) else ""
