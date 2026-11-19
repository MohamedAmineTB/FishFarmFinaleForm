"""Creating farms, basins and team members. Used by the API and by the demo seed."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import DEFAULT_PERMISSIONS
from ..domain import load_thresholds, sensor_range
from ..models import Basin, Owner, Sensor, SimulatorState, User, UserRole
from ..pipeline.model import METRICS, TYPE_OF, default_profile
from ..security import hash_password


class EmailTaken(Exception):
    pass


def email_exists(db: Session, email: str) -> bool:
    return db.scalar(select(User.id).where(func.lower(User.email) == email.lower())) is not None


def create_owner(
    db: Session,
    *,
    name: str,
    email: str,
    password: str,
    farm_name: str,
    company: str,
    country: str,
    timezone: str = "Europe/Paris",
) -> User:
    if email_exists(db, email):
        raise EmailTaken(email)
    user = User(email=email.lower(), password_hash=hash_password(password), name=name)
    db.add(user)
    db.flush()
    db.add(Owner(user_id=user.id, farm_name=farm_name, company_name=company, country=country, timezone=timezone))
    db.add(UserRole(user_id=user.id, owner_user_id=user.id, role="owner", permissions={}))
    db.add(SimulatorState(owner_user_id=user.id, paused=False))
    db.flush()
    return user


def create_member(
    db: Session,
    owner_id: uuid.UUID,
    *,
    name: str,
    email: str,
    password: str,
    role: str,
    shift_start: str,
    shift_end: str,
    permissions: dict | None = None,
) -> User:
    if email_exists(db, email):
        raise EmailTaken(email)
    user = User(email=email.lower(), password_hash=hash_password(password), name=name)
    db.add(user)
    db.flush()
    db.add(
        UserRole(
            user_id=user.id,
            owner_user_id=owner_id,
            role=role,
            permissions=permissions or dict(DEFAULT_PERMISSIONS[role]),
            shift_start=shift_start,
            shift_end=shift_end,
        )
    )
    db.flush()
    return user


def next_sensor_number(db: Session, owner_id: uuid.UUID) -> int:
    codes = db.scalars(select(Sensor.code).where(Sensor.owner_user_id == owner_id)).all()
    nums = [int(c.split("-")[1]) for c in codes if c.startswith("S-") and c[2:].isdigit()]
    return (max(nums) if nums else 0) + 1


def create_basin(
    db: Session,
    owner_id: uuid.UUID,
    *,
    name: str,
    species: str,
    capacity: float,
    fish_count: int,
    revenue: float = 0,
    feed: float = 0,
    maint: float = 0,
    ops: float = 0,
    profile: dict | None = None,
    calibrated: list[datetime] | None = None,
) -> Basin:
    """Creates the basin and its 3 probes (temperature, pH, oxygen) with the species safe ranges."""
    position = (db.scalar(select(func.max(Basin.position)).where(Basin.owner_user_id == owner_id)) or 0) + 1
    basin = Basin(
        owner_user_id=owner_id,
        name=name,
        species=species,
        capacity=capacity,
        fish_count=fish_count,
        revenue=revenue,
        feeding_cost=feed,
        maintenance_cost=maint,
        operational_cost=ops,
        sim_profile=profile or default_profile(species),
        position=position,
        status="healthy",
    )
    db.add(basin)
    db.flush()
    th = load_thresholds(db)[species]
    n = next_sensor_number(db, owner_id)
    now = datetime.now(UTC)
    for i, m in enumerate(METRICS):
        lo, hi = sensor_range(th, TYPE_OF[m])
        db.add(
            Sensor(
                owner_user_id=owner_id,
                basin_id=basin.id,
                code=f"S-{n + i:02d}",
                type=TYPE_OF[m],
                min_value=lo,
                max_value=hi,
                last_calibrated_at=(calibrated[i] if calibrated else now),
            )
        )
    db.flush()
    return basin
