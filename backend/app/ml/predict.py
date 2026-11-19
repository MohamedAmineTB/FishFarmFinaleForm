"""Live oxygen-drop prediction for a basin (used by the API, the pipeline and the assistant)."""

import logging
import threading
from datetime import UTC, datetime, timedelta

import joblib
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..domain import load_thresholds
from ..models import Basin, Owner, Prediction
from .features import DISPLAY, FEATURES, compute_features, load_series
from .train import model_dir, train

log = logging.getLogger("fishfarm.ml")
_lock = threading.Lock()
_cache: dict = {}


def load_model(db: Session | None = None) -> dict | None:
    """Loads ml/artifacts/model.joblib; trains it first if it does not exist yet (a few seconds)."""
    path = model_dir() / "model.joblib"
    with _lock:
        if path.exists():
            mtime = path.stat().st_mtime
            if _cache.get("mtime") != mtime:
                _cache.update(bundle=joblib.load(path), mtime=mtime)
            return _cache["bundle"]
        if db is None:
            return None
        try:
            log.info("no model found: training one from the history in the database")
            train(db)
        except RuntimeError as e:
            log.warning("cannot train yet: %s", e)
            return None
    return load_model()


def predict_basin(db: Session, basin: Basin, store: bool = False) -> Prediction | None:
    bundle = load_model(db)
    th = load_thresholds(db)[basin.species]
    if bundle is None or th.do_warn is None:
        return None
    owner = db.get(Owner, basin.owner_user_id)
    tz = owner.timezone if owner else "Europe/Paris"
    series = load_series(db, [basin.id], datetime.now(UTC) - timedelta(hours=26)).get(basin.id)
    if series is None or "do" not in series or len(series) < 24:
        return None
    f = compute_features(series, fish=basin.fish_count, capacity=basin.capacity, warn=th.do_warn, tz=tz)
    row = f.iloc[[-1]][FEATURES].ffill()
    if row.isna().any(axis=None):
        row = f[FEATURES].ffill().iloc[[-1]]
        if row.isna().any(axis=None):
            return None
    prob = float(bundle["model"].predict_proba(row)[0, 1])
    last = f.iloc[-1]
    top = []
    for label, unit, col in DISPLAY:
        v = float(last[col])
        top.append(
            {
                "name": col,
                "label": label,
                "unit": unit,
                "value": round(v, 2) if col == "do_decline_3h" else round(v, 1) if col == "temp_now" else round(v),
            }
        )
    p = Prediction(
        owner_user_id=basin.owner_user_id,
        basin_id=basin.id,
        probability=prob,
        horizon="before 06:00 (local time)",
        features={k: round(float(last[k]), 4) for k in FEATURES},
        top_features=top,
        model_version=bundle.get("version", "v1"),
        created_at=datetime.now(UTC),
    )
    if store:
        db.add(p)
        db.flush()
    return p


def predict_all(db: Session) -> int:
    n = 0
    for b in db.scalars(select(Basin).where(Basin.status != "inactive")):
        if predict_basin(db, b, store=True):
            n += 1
    db.execute(delete(Prediction).where(Prediction.created_at < datetime.now(UTC) - timedelta(days=7)))
    return n
