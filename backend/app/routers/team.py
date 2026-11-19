"""Team management (owner only): list, add a member with a temporary password, edit permissions."""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from ..db import get_db, notify
from ..deps import DEFAULT_PERMISSIONS, PERMISSION_KEYS, Ctx, require_owner
from ..models import UserRole
from ..services.briefing import team
from ..services.farm import EmailTaken, create_member

router = APIRouter(prefix="/api/team", tags=["team"])
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@router.get("")
def list_team(ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    return team(db, ctx.owner_id)


class MemberIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(pattern="^(worker|technician)$")
    shift_start: str
    shift_end: str


@router.post("", status_code=201)
def add_member(body: MemberIn, ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    if not HHMM.match(body.shift_start) or not HHMM.match(body.shift_end):
        raise HTTPException(422, "Shift times must look like 06:00.")
    try:
        u = create_member(
            db,
            ctx.owner_id,
            name=body.name.strip(),
            email=body.email,
            password=body.password,
            role=body.role,
            shift_start=body.shift_start,
            shift_end=body.shift_end,
            permissions=dict(DEFAULT_PERMISSIONS[body.role]),
        )
    except EmailTaken as e:
        raise HTTPException(409, {"code": "email_taken", "message": "This email already has an account."}) from e
    notify(db, {"type": "team", "owner_id": str(ctx.owner_id), "action": "added", "user_id": str(u.id)})
    db.commit()
    return {"id": str(u.id), "name": u.name, "email": u.email}


class PermissionsIn(BaseModel):
    permissions: dict[str, bool]


@router.patch("/{user_id}/permissions")
def set_permissions(user_id: uuid.UUID, body: PermissionsIn, ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    r = db.get(UserRole, user_id)
    if not r or r.owner_user_id != ctx.owner_id or r.role == "owner":
        raise HTTPException(404, "Team member not found.")
    unknown = set(body.permissions) - set(PERMISSION_KEYS)
    if unknown:
        raise HTTPException(422, f"Unknown permissions: {', '.join(sorted(unknown))}")
    r.permissions = {**r.permissions, **body.permissions}
    # pushed live: the member's menu updates without a refresh
    notify(db, {"type": "permissions", "owner_id": str(ctx.owner_id), "user_id": str(user_id), "permissions": r.permissions})
    db.commit()
    return {"permissions": r.permissions}
