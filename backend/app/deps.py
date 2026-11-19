"""Request dependencies: who is calling, which farm they belong to, and what they may do.

Multi-tenancy rule: every query is filtered by `ctx.owner_id`, which comes from the
database row of the signed-in user, never from the request body.
"""

import uuid
from dataclasses import dataclass, field

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .db import get_db
from .models import Owner, User, UserRole
from .security import decode_access_token

PERMISSION_KEYS = ("reports", "alerts", "basins", "sensors", "maintenance")

DEFAULT_PERMISSIONS = {
    "worker": {"reports": True, "alerts": True, "basins": True, "sensors": False, "maintenance": False},
    "technician": {"reports": True, "alerts": True, "basins": False, "sensors": True, "maintenance": True},
}


@dataclass
class Ctx:
    user: User
    role: str
    owner_id: uuid.UUID
    permissions: dict = field(default_factory=dict)
    shift_start: str | None = None
    shift_end: str | None = None

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    def can(self, perm: str) -> bool:
        return self.is_owner or bool(self.permissions.get(perm))


def has_role(db: Session, role: str, user_id: uuid.UUID) -> bool:
    r = db.get(UserRole, user_id)
    return bool(r and r.role == role)


def get_owner_for_user(db: Session, user_id: uuid.UUID) -> uuid.UUID | None:
    r = db.get(UserRole, user_id)
    return r.owner_user_id if r else None


def load_ctx(db: Session, user_id: uuid.UUID) -> Ctx | None:
    user = db.get(User, user_id)
    role = db.get(UserRole, user_id)
    if not user or not role:
        return None
    return Ctx(
        user=user,
        role=role.role,
        owner_id=role.owner_user_id,
        permissions=dict(role.permissions or {}),
        shift_start=role.shift_start,
        shift_end=role.shift_end,
    )


def current_ctx(request: Request, db: Session = Depends(get_db)) -> Ctx:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    try:
        data = decode_access_token(auth[7:])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired.") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session.") from e
    ctx = load_ctx(db, uuid.UUID(data["sub"]))
    if ctx is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found.")
    return ctx


def require_owner(ctx: Ctx = Depends(current_ctx)) -> Ctx:
    if not ctx.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the farm owner can do this.")
    return ctx


def require_perm(perm: str):
    """Dependency factory: owners always pass; team members need the permission switched on."""

    def dep(ctx: Ctx = Depends(current_ctx)) -> Ctx:
        if not ctx.can(perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"You don't have access to {perm}. Ask your farm owner.")
        return ctx

    return dep


def farm_of(db: Session, ctx: Ctx) -> Owner:
    farm = db.get(Owner, ctx.owner_id)
    if farm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Farm not found.")
    return farm
