"""Alerts: list (Open / Done), resolve with a note, reopen."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db, notify
from ..deps import Ctx, require_perm
from ..models import Alert, Basin, Sensor
from ..services.views import alert_json, alerts_for, role_alert_kind

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    status: str = Query("open", pattern="^(open|resolved|all)$"),
    ctx: Ctx = Depends(require_perm("alerts")),
    db: Session = Depends(get_db),
):
    kind = role_alert_kind(ctx.role)
    if status == "all":
        return alerts_for(db, ctx.owner_id, kind=kind)
    return alerts_for(db, ctx.owner_id, kind=kind, resolved=(status == "resolved"))


def _get(db: Session, ctx: Ctx, alert_id: uuid.UUID) -> Alert:
    a = db.get(Alert, alert_id)
    kind = role_alert_kind(ctx.role)
    if not a or a.owner_user_id != ctx.owner_id or (kind and a.kind != kind):
        raise HTTPException(404, "Alert not found.")
    return a


def _out(db: Session, a: Alert) -> dict:
    basins = {a.basin_id: db.get(Basin, a.basin_id)}
    names = {}
    if a.resolved_by:
        from ..models import User

        u = db.get(User, a.resolved_by)
        names = {u.id: u.name} if u else {}
    return alert_json(a, basins, names)


class ResolveIn(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


@router.post("/{alert_id}/resolve")
def resolve(alert_id: uuid.UUID, body: ResolveIn, ctx: Ctx = Depends(require_perm("alerts")), db: Session = Depends(get_db)):
    a = _get(db, ctx, alert_id)
    if a.is_resolved:
        raise HTTPException(409, "This alert is already resolved.")
    now = datetime.now(UTC)
    a.is_resolved, a.resolved_by, a.resolved_at, a.resolution_note = True, ctx.user.id, now, body.note.strip()
    if a.kind == "sensor" and a.sensor_id:
        # the technician repaired the probe: clear the simulated fault and record the calibration
        s = db.get(Sensor, a.sensor_id)
        if s:
            s.sim_fault, s.last_calibrated_at, s.health, s.health_note = None, now, "ok", "Repaired, waiting for new readings"
    db.flush()
    db.execute(text("SELECT ff_refresh_basin_status(:b)"), {"b": a.basin_id})
    notify(
        db,
        {
            "type": "alert",
            "action": "resolved",
            "owner_id": str(ctx.owner_id),
            "alert_id": str(a.id),
            "kind": a.kind,
            "by": ctx.user.name,
        },
    )
    db.commit()
    return _out(db, a)


@router.post("/{alert_id}/reopen")
def reopen(alert_id: uuid.UUID, ctx: Ctx = Depends(require_perm("alerts")), db: Session = Depends(get_db)):
    a = _get(db, ctx, alert_id)
    a.is_resolved, a.resolved_by, a.resolved_at, a.resolution_note = False, None, None, None
    db.flush()
    db.execute(text("SELECT ff_refresh_basin_status(:b)"), {"b": a.basin_id})
    notify(db, {"type": "alert", "action": "reopened", "owner_id": str(ctx.owner_id), "alert_id": str(a.id), "kind": a.kind})
    db.commit()
    return _out(db, a)
