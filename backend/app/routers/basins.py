"""Basins: list, detail, 24-hour readings, finances, creation and the oxygen prediction."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db, notify
from ..deps import Ctx, require_owner, require_perm
from ..domain import METRIC_INFO, SPECIES_CODES, load_thresholds
from ..models import Basin, Sensor, SimulatorState
from ..services.farm import create_basin
from ..services.views import (
    alerts_for,
    basin_json,
    basins_with_sensors,
    finance_json,
    latest_predictions,
    live_basins,
    overnight_low,
    series_24h,
)

router = APIRouter(prefix="/api/basins", tags=["basins"])


def get_basin(db: Session, ctx: Ctx, basin_id: uuid.UUID) -> Basin:
    """Tenant-safe lookup: a basin of another farm is reported as 'not found'."""
    b = db.get(Basin, basin_id)
    if not b or b.owner_user_id != ctx.owner_id:
        raise HTTPException(404, "Basin not found.")
    return b


@router.get("")
def list_basins(ctx: Ctx = Depends(require_perm("basins")), db: Session = Depends(get_db)):
    return live_basins(db, ctx.owner_id, with_finance=ctx.is_owner)


class BasinIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    species: str
    capacity: float = Field(gt=0, le=1_000_000)
    fish_count: int = Field(ge=0, le=10_000_000)


@router.post("", status_code=201)
def add_basin(body: BasinIn, ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    if body.species not in SPECIES_CODES:
        raise HTTPException(422, "Unknown species.")
    b = create_basin(db, ctx.owner_id, name=body.name.strip(), species=body.species, capacity=body.capacity,
                     fish_count=body.fish_count)
    if not db.get(SimulatorState, ctx.owner_id):
        db.add(SimulatorState(owner_user_id=ctx.owner_id, paused=False))
    notify(db, {"type": "farm", "owner_id": str(ctx.owner_id), "action": "basin_created", "basin_id": str(b.id)})
    db.commit()
    return {"id": str(b.id)}


@router.get("/{basin_id}")
def basin_detail(basin_id: uuid.UUID, ctx: Ctx = Depends(require_perm("basins")), db: Session = Depends(get_db)):
    b = get_basin(db, ctx, basin_id)
    th = load_thresholds(db)[b.species]
    sensors = dict(next(s for bb, s in basins_with_sensors(db, ctx.owner_id) if bb.id == b.id))
    pred = latest_predictions(db, ctx.owner_id).get(b.id)
    out = basin_json(b, sensors, th, pred, with_finance=ctx.is_owner)
    low = overnight_low(series_24h(db, sensors["do"])) if "do" in sensors else None
    out["overnight_low"] = low
    out["prediction"] = _prediction_json(pred, b) if pred else None
    out["probes"] = [{"id": str(s.id), "code": s.code, "metric": m, "label": METRIC_INFO[m]["label"],
                      "health": s.health, "note": s.health_note}
                     for m, s in sorted(sensors.items(), key=lambda kv: kv[1].code)]
    out["alerts"] = alerts_for(db, ctx.owner_id, basin_id=b.id)[:4]
    return out


@router.get("/{basin_id}/readings")
def readings(basin_id: uuid.UUID, metric: str = Query("do", pattern="^(do|temp|ph)$"),
             ctx: Ctx = Depends(require_perm("basins")), db: Session = Depends(get_db)):
    b = get_basin(db, ctx, basin_id)
    sensor = db.scalar(select(Sensor).where(Sensor.basin_id == b.id, Sensor.type == {
        "do": "oxygen", "temp": "temperature", "ph": "ph"}[metric]))
    if not sensor:
        raise HTTPException(404, "No probe for this metric.")
    return {"metric": metric, **series_24h(db, sensor, datetime.now(UTC))}


class FinanceIn(BaseModel):
    fish: int = Field(ge=0, le=10_000_000)
    feed: float = Field(ge=0, le=1e9)
    maint: float = Field(ge=0, le=1e9)
    ops: float = Field(ge=0, le=1e9)


@router.put("/{basin_id}/finances")
def save_finances(basin_id: uuid.UUID, body: FinanceIn, ctx: Ctx = Depends(require_owner),
                  db: Session = Depends(get_db)):
    b = get_basin(db, ctx, basin_id)
    b.fish_count, b.feeding_cost, b.maintenance_cost, b.operational_cost = body.fish, body.feed, body.maint, body.ops
    notify(db, {"type": "farm", "owner_id": str(ctx.owner_id), "action": "finance", "basin_id": str(b.id)})
    db.commit()
    return finance_json(b)


def _prediction_json(p, b: Basin) -> dict:
    return {"probability": round(p.probability, 3), "horizon": p.horizon, "features": p.features,
            "top_features": p.top_features, "model_version": p.model_version, "created_at": p.created_at.isoformat(),
            "is_estimate": True}


@router.get("/{basin_id}/prediction")
def prediction(basin_id: uuid.UUID, ctx: Ctx = Depends(require_perm("basins")), db: Session = Depends(get_db)):
    b = get_basin(db, ctx, basin_id)
    from ..ml.predict import predict_basin

    p = predict_basin(db, b, store=True)
    db.commit()
    if p is None:
        raise HTTPException(503, "Not enough data for a prediction yet (needs a few hours of readings).")
    return _prediction_json(p, b)
