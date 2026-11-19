"""Machine learning: label definition, feature windows, training metrics, prediction endpoint."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.db import session_scope
from app.ml.features import FEATURES, compute_features, labels
from app.ml.train import train


def _series(days=3, night_low=4.0):
    idx = pd.date_range(datetime(2026, 6, 1, tzinfo=UTC), periods=days * 96, freq="15min")
    hours = idx.tz_convert("Europe/Paris").hour + idx.tz_convert("Europe/Paris").minute / 60
    do = 7 + (7 - night_low) * np.cos(2 * np.pi * (hours - 15.5) / 24)
    return pd.DataFrame({"do": do, "temp": 25.0, "ph": 7.5}, index=idx)


def test_label_looks_until_next_six_am():
    s = _series(night_low=4.0)
    y = labels(s, warn=5.0, tz="Europe/Paris")
    # every complete window contains a pre-dawn low of about 4 mg/L < 5
    assert y.dropna().eq(1).all()
    calm = labels(_series(night_low=6.0), warn=5.0, tz="Europe/Paris")
    assert calm.dropna().eq(0).all()
    # the last hours have no complete window yet
    assert np.isnan(y.iloc[-1])


def test_features_only_use_the_past():
    s = _series()
    f = compute_features(s, fish=1000, capacity=100, warn=5.0, tz="Europe/Paris")
    assert set(FEATURES) <= set(f.columns)
    # changing the future must not change today's features
    s2 = s.copy()
    s2.iloc[200:, s2.columns.get_loc("do")] = 0
    f2 = compute_features(s2, fish=1000, capacity=100, warn=5.0, tz="Europe/Paris")
    pd.testing.assert_frame_equal(f.iloc[:199], f2.iloc[:199])
    assert f["feed_kg_per_m3"].iloc[0] == 1000 * 0.012 / 100


def test_training_reports_time_split_metrics(client):
    with session_scope() as db:
        m = train(db, save=False)
    assert m["samples"]["train"] > m["samples"]["test"] > 100
    for key in ("precision", "recall", "f1", "confusion_matrix"):
        assert key in m["model"]
    assert m["model"]["recall"] >= 0.6  # most nightly dips are caught (weather differs per seed)
    assert "baseline_last_24h_dip" in m


def test_prediction_endpoint(client, owner_h):
    b3 = next(b for b in client.get("/api/basins", headers=owner_h).json() if b["name"] == "Basin 3")
    r = client.get(f"/api/basins/{b3['id']}/prediction", headers=owner_h)
    assert r.status_code == 200, r.text
    p = r.json()
    assert 0 <= p["probability"] <= 1 and p["is_estimate"] is True
    assert [f["label"] for f in p["top_features"]] == ["Evening oxygen decline", "Water temperature", "Evening feed"]
    assert p["probability"] > 0.5  # Basin 3 dips under 7.0 mg/L most nights
    detail = client.get(f"/api/basins/{b3['id']}", headers=owner_h).json()
    assert detail["prediction"]["model_version"]
