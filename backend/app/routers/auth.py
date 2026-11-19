"""Authentication: register an owner (creates a farm), sign in owner / team, refresh, sign out."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import Ctx, current_ctx, load_ctx
from ..models import RefreshToken, User, UserRole
from ..security import create_access_token, hash_refresh_token, new_refresh_token, verify_password
from ..services.farm import EmailTaken, create_owner

router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE = "ff_refresh"


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    farm: str = Field(min_length=1, max_length=120)
    company: str = Field(min_length=1, max_length=160)
    country: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    portal: str = Field(pattern="^(owner|team)$")


def _session(db: Session, response: Response, user: User) -> dict:
    s = get_settings()
    ctx = load_ctx(db, user.id)
    token, digest = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=digest,
                        expires_at=datetime.now(UTC) + timedelta(days=s.refresh_token_days)))
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, secure=s.cookie_secure, samesite="lax", path="/api/auth",
                        max_age=s.refresh_token_days * 86400)
    return {"access_token": create_access_token(user.id, ctx.role, ctx.owner_id), "role": ctx.role}


@router.post("/register")
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)):
    try:
        user = create_owner(db, name=body.name.strip(), email=body.email, password=body.password,
                            farm_name=body.farm.strip(), company=body.company.strip(), country=body.country)
    except EmailTaken as e:
        raise HTTPException(409, {"code": "email_taken", "message": "This email already has an account."}) from e
    db.commit()
    return _session(db, response, user)


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, {"code": "bad_credentials",
                                  "message": "Wrong email or password. Check both, or use a demo account below."})
    role = db.get(UserRole, user.id)
    if body.portal == "owner" and role.role != "owner":
        raise HTTPException(403, {"code": "wrong_portal", "role": role.role,
                                  "message": f"This is a {role.role} account. Use team sign in."})
    if body.portal == "team" and role.role == "owner":
        raise HTTPException(403, {"code": "wrong_portal", "role": "owner",
                                  "message": "This is an owner account. Use owner sign in."})
    return _session(db, response, user)


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "No session.")
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token)))
    if not row or row.revoked_at or row.expires_at < datetime.now(UTC):
        raise HTTPException(401, "Session expired.")
    # rotate: the old refresh token can't be used twice
    row.revoked_at = datetime.now(UTC)
    user = db.get(User, row.user_id)
    return _session(db, response, user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    if token:
        row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token)))
        if row and not row.revoked_at:
            row.revoked_at = datetime.now(UTC)
            db.commit()
    response.delete_cookie(COOKIE, path="/api/auth")
    return {"ok": True}


@router.get("/me")
def me(ctx: Ctx = Depends(current_ctx)):
    return {"id": str(ctx.user.id), "name": ctx.user.name, "email": ctx.user.email, "role": ctx.role}
