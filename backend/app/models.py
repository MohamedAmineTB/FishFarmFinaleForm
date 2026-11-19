"""SQLAlchemy ORM models. The schema itself (enums, trigger, RLS, views) lives in Alembic migrations."""

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

AppRole = ENUM("owner", "worker", "technician", name="app_role", create_type=False)
BasinStatus = ENUM("healthy", "warning", "critical", "inactive", name="basin_status", create_type=False)
SensorType = ENUM("temperature", "ph", "oxygen", name="sensor_type", create_type=False)
SensorStatus = ENUM("active", "inactive", "maintenance", name="sensor_status", create_type=False)
AlertSeverity = ENUM("low", "medium", "high", "critical", name="alert_severity", create_type=False)
TaskStatus = ENUM("pending", "in_progress", "fixed", name="task_status", create_type=False)


def _uuid() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = _now()


class Owner(Base):
    __tablename__ = "owners"
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    farm_name: Mapped[str] = mapped_column(String(120))
    company_name: Mapped[str] = mapped_column(String(160))
    country: Mapped[str] = mapped_column(String(80))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Paris")
    created_at: Mapped[datetime] = _now()


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(AppRole)
    permissions: Mapped[dict] = mapped_column(JSONB, default=dict)
    shift_start: Mapped[str | None] = mapped_column(String(5))
    shift_end: Mapped[str | None] = mapped_column(String(5))
    created_at: Mapped[datetime] = _now()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = _uuid()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


class SpeciesThreshold(Base):
    __tablename__ = "species_thresholds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    species: Mapped[str] = mapped_column(String(40))
    metric: Mapped[str] = mapped_column(String(20))  # oxygen | temperature | ph | oxygen_saturation
    unit: Mapped[str] = mapped_column(String(10))
    optimal_min: Mapped[float | None] = mapped_column(Float)
    optimal_max: Mapped[float | None] = mapped_column(Float)
    warning_min: Mapped[float | None] = mapped_column(Float)
    warning_max: Mapped[float | None] = mapped_column(Float)
    critical_min: Mapped[float | None] = mapped_column(Float)
    critical_max: Mapped[float | None] = mapped_column(Float)
    emergency_min: Mapped[float | None] = mapped_column(Float)
    source_label: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[str] = mapped_column(String(400))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)


class Basin(Base):
    __tablename__ = "basins"
    id: Mapped[uuid.UUID] = _uuid()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    species: Mapped[str] = mapped_column(String(40))
    capacity: Mapped[float] = mapped_column(Float)
    fish_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(BasinStatus, default="healthy")
    revenue: Mapped[float] = mapped_column(Float, default=0)
    feeding_cost: Mapped[float] = mapped_column(Float, default=0)
    maintenance_cost: Mapped[float] = mapped_column(Float, default=0)
    operational_cost: Mapped[float] = mapped_column(Float, default=0)
    sim_profile: Mapped[dict] = mapped_column(JSONB, default=dict)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Sensor(Base):
    __tablename__ = "sensors"
    id: Mapped[uuid.UUID] = _uuid()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    basin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("basins.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(12))
    type: Mapped[str] = mapped_column(SensorType)
    status: Mapped[str] = mapped_column(SensorStatus, default="active")
    min_value: Mapped[float | None] = mapped_column(Float)
    max_value: Mapped[float | None] = mapped_column(Float)
    last_value: Mapped[float | None] = mapped_column(Float)
    last_reading_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_calibrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health: Mapped[str] = mapped_column(String(12), default="ok")
    health_note: Mapped[str | None] = mapped_column(Text)
    sim_fault: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Reading(Base):
    __tablename__ = "readings"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sensor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sensors.id", ondelete="CASCADE"))
    value: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[uuid.UUID] = _uuid()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    basin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("basins.id", ondelete="CASCADE"))
    sensor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sensors.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(10))  # water | sensor
    metric: Mapped[str] = mapped_column(String(20))
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(AlertSeverity)
    value: Mapped[float | None] = mapped_column(Float)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()


class Maintenance(Base):
    __tablename__ = "maintenance"
    id: Mapped[uuid.UUID] = _uuid()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    technician_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    sensor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sensors.id", ondelete="SET NULL"))
    work_type: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _now()


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = _uuid()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(12))  # shift | maintenance
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    basin_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("basins.id", ondelete="SET NULL"))
    content: Mapped[dict] = mapped_column(JSONB, default=dict)
    generated_at: Mapped[datetime] = _now()


class ReportRead(Base):
    __tablename__ = "report_reads"
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"),
                                                 primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    read_at: Mapped[datetime] = _now()


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = _uuid()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    basin_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("basins.id", ondelete="SET NULL"))
    sensor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sensors.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(TaskStatus, default="pending")
    source: Mapped[str] = mapped_column(String(12), default="manual")  # manual | assistant | maintenance
    due_date: Mapped[date | None] = mapped_column(Date)
    due_label: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SimulatorState(Base):
    __tablename__ = "simulator_state"
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                                     primary_key=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EtlRun(Base):
    __tablename__ = "etl_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = _now()
    source: Mapped[str] = mapped_column(String(20))
    received: Mapped[int] = mapped_column(Integer)
    accepted: Mapped[int] = mapped_column(Integer)
    rejected: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[dict] = mapped_column(JSONB, default=dict)


class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    basin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("basins.id", ondelete="CASCADE"))
    probability: Mapped[float] = mapped_column(Float)
    horizon: Mapped[str] = mapped_column(String(40))
    features: Mapped[dict] = mapped_column(JSONB)
    top_features: Mapped[list] = mapped_column(JSONB)
    model_version: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = _now()
