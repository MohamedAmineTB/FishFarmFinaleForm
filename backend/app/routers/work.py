"""Tasks, maintenance logs and sensor health."""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..db import get_db, notify
from ..deps import Ctx, current_ctx, require_perm
from ..domain import METRIC_INFO, TYPE_TO_METRIC
from ..models import Basin, Maintenance, Report, Sensor, Task
from ..services.briefing import tasks_json

router = APIRouter(prefix="/api", tags=["work"])

STATUS_IN = {"pending": "pending", "in progress": "in_progress", "in_progress": "in_progress", "fixed": "fixed"}


@router.get("/tasks")
def list_tasks(
    scope: str = Query("mine", pattern="^(mine|all)$"), ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)
):
    if scope == "all":
        if not ctx.can("maintenance"):
            raise HTTPException(403, "You don't have access to maintenance. Ask your farm owner.")
        return tasks_json(db, ctx.owner_id)
    return tasks_json(db, ctx.owner_id, assignee=ctx.user.id)


class TaskStatusIn(BaseModel):
    status: str


@router.patch("/tasks/{task_id}")
def update_task(task_id: uuid.UUID, body: TaskStatusIn, ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if not t or t.owner_user_id != ctx.owner_id:
        raise HTTPException(404, "Task not found.")
    if not (t.assignee_user_id == ctx.user.id or ctx.can("maintenance")):
        raise HTTPException(403, "Only the person assigned, a technician or the owner can update this task.")
    st = STATUS_IN.get(body.status)
    if not st:
        raise HTTPException(422, "Status must be pending, in progress or fixed.")
    t.status = st
    notify(
        db,
        {
            "type": "task",
            "action": "updated",
            "owner_id": str(ctx.owner_id),
            "task_id": str(t.id),
            "assignee_id": str(t.assignee_user_id) if t.assignee_user_id else None,
        },
    )
    db.commit()
    return {"id": str(t.id), "status": t.status}


@router.get("/sensors")
def sensors(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    """Sensor health table with a 6-hour sparkline (15-minute means) per probe."""
    if not (ctx.can("sensors") or ctx.can("maintenance")):
        raise HTTPException(403, "You don't have access to sensors. Ask your farm owner.")
    now = datetime.now(UTC)
    rows = db.scalars(select(Sensor).where(Sensor.owner_user_id == ctx.owner_id).order_by(Sensor.code)).all()
    basins = {b.id: b for b in db.scalars(select(Basin).where(Basin.owner_user_id == ctx.owner_id))}
    start = now - timedelta(hours=6)
    spark = db.execute(
        text(
            "SELECT sensor_id, floor(extract(epoch FROM (recorded_at - :a)) / 900)::int AS k, avg(value) "
            "FROM readings WHERE owner_user_id = :o AND recorded_at > :a GROUP BY 1, 2 ORDER BY 1, 2"
        ),
        {"o": ctx.owner_id, "a": start},
    ).all()
    by: dict = {}
    for sid, _k, v in spark:
        by.setdefault(sid, []).append(round(float(v), 3))
    out = []
    for s in rows:
        m = TYPE_TO_METRIC[s.type]
        b = basins.get(s.basin_id)
        out.append(
            {
                "id": str(s.id),
                "code": s.code,
                "basin": b.name if b else "",
                "basin_id": str(s.basin_id),
                "metric": m,
                "label": METRIC_INFO[m]["label"],
                "short": METRIC_INFO[m]["short"],
                "health": s.health,
                "note": s.health_note or "",
                "spark": by.get(s.id, []),
                "calibrated": s.last_calibrated_at.isoformat() if s.last_calibrated_at else None,
                "last_value": s.last_value,
            }
        )
    return out


class MaintenanceIn(BaseModel):
    sensor_id: uuid.UUID
    work_type: str = Field(pattern="^(Calibration|Repair|Replacement)$")
    due_date: date
    description: str = Field(min_length=1, max_length=5000)


@router.post("/maintenance", status_code=201)
def log_maintenance(body: MaintenanceIn, ctx: Ctx = Depends(require_perm("maintenance")), db: Session = Depends(get_db)):
    s = db.get(Sensor, body.sensor_id)
    if not s or s.owner_user_id != ctx.owner_id:
        raise HTTPException(404, "Probe not found.")
    b = db.get(Basin, s.basin_id)
    label = f"{s.code} · {b.name} · {METRIC_INFO[TYPE_TO_METRIC[s.type]]['short']}"
    now = datetime.now(UTC)
    db.add(
        Maintenance(
            owner_user_id=ctx.owner_id,
            technician_user_id=ctx.user.id,
            sensor_id=s.id,
            work_type=body.work_type,
            description=body.description.strip(),
            due_date=body.due_date,
        )
    )
    db.add(
        Task(
            owner_user_id=ctx.owner_id,
            title=f"{body.work_type}: {label}",
            assignee_user_id=ctx.user.id,
            basin_id=b.id,
            sensor_id=s.id,
            status="pending",
            source="maintenance",
            due_date=body.due_date,
            created_by=ctx.user.id,
        )
    )
    r = Report(
        owner_user_id=ctx.owner_id,
        author_user_id=ctx.user.id,
        kind="maintenance",
        title=f"{body.work_type}, {label}",
        body=body.description.strip(),
        basin_id=b.id,
        content={"sensor": s.code, "work_type": body.work_type, "due_date": body.due_date.isoformat()},
    )
    db.add(r)
    # the probe has been worked on: clear any simulated fault and record the calibration date
    s.sim_fault, s.last_calibrated_at = None, now
    db.flush()
    notify(
        db,
        {
            "type": "report",
            "action": "created",
            "owner_id": str(ctx.owner_id),
            "report_id": str(r.id),
            "title": r.title,
            "author": ctx.user.name,
        },
    )
    notify(db, {"type": "task", "action": "created", "owner_id": str(ctx.owner_id)})
    db.commit()
    return {"ok": True, "report_id": str(r.id)}
