"""Reports inbox (owner) with per-user read state, and shift reports sent by the team."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..db import get_db, notify
from ..deps import Ctx, require_owner, require_perm
from ..models import Basin, Report, ReportRead, User, UserRole

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _json(r: Report, author: User | None, role: str | None, read: bool) -> dict:
    return {
        "id": str(r.id),
        "title": r.title,
        "body": r.body,
        "kind": r.kind,
        "time": r.generated_at.isoformat(),
        "author": author.name if author else "Former member",
        "role": {"worker": "Worker", "technician": "Technician", "owner": "Owner"}.get(role or "", "Worker"),
        "read": read,
    }


@router.get("")
def inbox(ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Report, User, UserRole.role)
        .outerjoin(User, User.id == Report.author_user_id)
        .outerjoin(UserRole, UserRole.user_id == Report.author_user_id)
        .where(Report.owner_user_id == ctx.owner_id)
        .order_by(Report.generated_at.desc())
    ).all()
    read = set(db.scalars(select(ReportRead.report_id).where(ReportRead.user_id == ctx.user.id)))
    return [_json(r, u, role, r.id in read) for r, u, role in rows]


@router.get("/mine")
def mine(ctx: Ctx = Depends(require_perm("reports")), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Report)
        .where(Report.owner_user_id == ctx.owner_id, Report.author_user_id == ctx.user.id)
        .order_by(Report.generated_at.desc())
        .limit(20)
    ).all()
    return [_json(r, ctx.user, ctx.role, True) for r in rows]


class ShiftReportIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    basin_id: uuid.UUID | None = None


@router.post("", status_code=201)
def send_report(body: ShiftReportIn, ctx: Ctx = Depends(require_perm("reports")), db: Session = Depends(get_db)):
    text_ = body.body.strip()
    if body.basin_id:
        b = db.get(Basin, body.basin_id)
        if not b or b.owner_user_id != ctx.owner_id:
            raise HTTPException(404, "Basin not found.")
        text_ = f"{b.name}: {text_}"
    r = Report(
        owner_user_id=ctx.owner_id,
        author_user_id=ctx.user.id,
        kind="shift",
        title=body.title.strip(),
        body=text_,
        basin_id=body.basin_id,
    )
    db.add(r)
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
    db.commit()
    return _json(r, ctx.user, ctx.role, False)


def _own_report(db: Session, ctx: Ctx, report_id: uuid.UUID) -> Report:
    r = db.get(Report, report_id)
    if not r or r.owner_user_id != ctx.owner_id:
        raise HTTPException(404, "Report not found.")
    return r


@router.post("/{report_id}/read")
def mark_read(report_id: uuid.UUID, ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    _own_report(db, ctx, report_id)
    db.execute(insert(ReportRead).values(report_id=report_id, user_id=ctx.user.id).on_conflict_do_nothing())
    notify(db, {"type": "report", "action": "read", "owner_id": str(ctx.owner_id)})
    db.commit()
    return {"read": True}


@router.delete("/{report_id}/read")
def mark_unread(report_id: uuid.UUID, ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    _own_report(db, ctx, report_id)
    db.execute(delete(ReportRead).where(ReportRead.report_id == report_id, ReportRead.user_id == ctx.user.id))
    notify(db, {"type": "report", "action": "read", "owner_id": str(ctx.owner_id)})
    db.commit()
    return {"read": False}


@router.post("/read-all")
def mark_all_read(ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    ids = db.scalars(select(Report.id).where(Report.owner_user_id == ctx.owner_id)).all()
    if ids:
        db.execute(insert(ReportRead).values([{"report_id": i, "user_id": ctx.user.id} for i in ids]).on_conflict_do_nothing())
    notify(db, {"type": "report", "action": "read", "owner_id": str(ctx.owner_id)})
    db.commit()
    return {"marked": len(ids)}
