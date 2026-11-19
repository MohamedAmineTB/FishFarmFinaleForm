"""Train and evaluate the oxygen-drop model: `python -m app.ml.train`

- data: the 30-day history of every basin in the database (hourly samples)
- split: by time (the last 25 % of days are the test set), never shuffled, so the test
  measures how the model does on nights it has never seen
- model: random forest (scikit-learn), class_weight="balanced"
- baseline: "it dipped under the warning level in the last 24 h, so it will again"
- output: ml/artifacts/model.joblib + ml/artifacts/metrics.json
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import session_scope
from ..domain import load_thresholds
from ..models import Basin, Owner
from .features import FEATURES, compute_features, labels, load_series

MODEL_VERSION = "v1.3"


def model_dir() -> Path:
    d = Path(get_settings().model_dir)
    if not d.is_absolute():
        d = (Path(__file__).resolve().parents[2] / d).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_dataset(db: Session, days: int = 30) -> pd.DataFrame:
    th = load_thresholds(db)
    tz = {o.user_id: o.timezone for o in db.scalars(select(Owner))}
    basins = db.scalars(select(Basin)).all()
    series = load_series(db, [b.id for b in basins], datetime.now(UTC) - timedelta(days=days))
    frames = []
    for b in basins:
        s = series.get(b.id)
        warn = th[b.species].do_warn
        if s is None or warn is None or "do" not in s or len(s) < 200:
            continue
        zone = tz.get(b.owner_user_id, "Europe/Paris")
        f = compute_features(s, fish=b.fish_count, capacity=b.capacity, warn=warn, tz=zone)
        f["label"] = labels(s, warn=warn, tz=zone)
        f["basin"] = b.name
        f = f[f.index.minute == 0]  # hourly samples
        frames.append(f)
    data = pd.concat(frames) if frames else pd.DataFrame()
    return data.dropna(subset=FEATURES + ["label"])


def evaluate(y_true, y_pred, y_prob=None) -> dict:
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    out = {
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 3),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 3),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 3),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 3),
        "confusion_matrix": {"tn": int(cm[0, 0]), "fp": int(cm[0, 1]), "fn": int(cm[1, 0]), "tp": int(cm[1, 1])},
    }
    if y_prob is not None and len(set(y_true)) > 1:
        out["roc_auc"] = round(float(roc_auc_score(y_true, y_prob)), 3)
    return out


def train(db: Session, save: bool = True) -> dict:
    data = build_dataset(db).sort_index()
    if len(data) < 100 or data["label"].nunique() < 2:
        raise RuntimeError("Not enough labelled history to train (load the demo farm first).")
    cut = data.index.min() + (data.index.max() - data.index.min()) * 0.75
    train_df, test_df = data[data.index < cut], data[data.index >= cut]
    model = RandomForestClassifier(
        n_estimators=300, max_depth=8, min_samples_leaf=4, class_weight="balanced", random_state=0, n_jobs=-1
    )
    model.fit(train_df[FEATURES], train_df["label"].astype(int))
    prob = model.predict_proba(test_df[FEATURES])[:, 1]
    pred = (prob >= 0.5).astype(int)
    y = test_df["label"].astype(int).to_numpy()
    baseline = (test_df["do_min_24h_gap"] < 0).astype(int).to_numpy()
    metrics = {
        "model_version": MODEL_VERSION,
        "trained_at": datetime.now(UTC).isoformat(),
        "samples": {
            "train": int(len(train_df)),
            "test": int(len(test_df)),
            "positive_rate": round(float(data["label"].mean()), 3),
        },
        "split": f"by time: train before {cut:%Y-%m-%d %H:%M} UTC, test after",
        "model": evaluate(y, pred, prob),
        "baseline_last_24h_dip": evaluate(y, baseline),
        "feature_importance": {
            k: round(float(v), 3)
            for k, v in sorted(zip(FEATURES, model.feature_importances_, strict=True), key=lambda kv: -kv[1])
        },
        "per_basin_test_positive_rate": {k: round(float(v), 2) for k, v in test_df.groupby("basin")["label"].mean().items()},
    }
    if save:
        d = model_dir()
        # refit on all data for production use (the metrics above come from the held-out period)
        final = RandomForestClassifier(
            n_estimators=300, max_depth=8, min_samples_leaf=4, class_weight="balanced", random_state=0, n_jobs=-1
        )
        final.fit(data[FEATURES], data["label"].astype(int))
        joblib.dump(
            {
                "model": final,
                "features": FEATURES,
                "version": MODEL_VERSION,
                "importance": dict(zip(FEATURES, final.feature_importances_, strict=True)),
            },
            d / "model.joblib",
        )
        (d / "metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def main() -> None:
    with session_scope() as db:
        m = train(db)
    print(json.dumps({k: m[k] for k in ("samples", "model", "baseline_last_24h_dip")}, indent=2))


if __name__ == "__main__":
    main()
