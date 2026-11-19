"""Farm-wide endpoints: profile, live state, home screens, simulator switch, demo loader."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db, notify
from ..deps import Ctx, current_ctx, farm_of, require_owner
from ..models import Basin, Report, ReportRead, Sensor, SimulatorState, UserRole
from ..services import briefing as br
from ..services.demo import load_demo
from ..services.views import SEV_RANK, alerts_for, live_basins, role_alert_kind

router = APIRouter(prefix="/api", tags=["farm"])


@router.get("/me")
def me(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    farm = farm_of(db, ctx)
    s = get_settings()
    return {
        "user": {"id": str(ctx.user.id), "name": ctx.user.name, "email": ctx.user.email},
        "role": ctx.role, "permissions": ctx.permissions,
        "shift": {"start": ctx.shift_start, "end": ctx.shift_end} if ctx.shift_start else None,
        "farm": {"name": farm.farm_name, "company": farm.company_name, "country": farm.country,
                 "timezone": farm.timezone},
        "assistant": {"provider": s.effective_llm_provider, "demo_mode": s.effective_llm_provider == "mock"},
    }


def _sim_paused(db: Session, ctx: Ctx) -> bool:
    st = db.get(SimulatorState, ctx.owner_id)
    return bool(st and st.paused)


@router.get("/live")
def live(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    """Small, frequently refreshed state for every page: basin statuses and live values, alert counts."""
    basins = live_basins(db, ctx.owner_id)
    kind = role_alert_kind(ctx.role)
    alerts = alerts_for(db, ctx.owner_id, resolved=False, kind=kind) if ctx.can("alerts") or ctx.is_owner else []
    unread = 0
    if ctx.is_owner:
        total = db.scalar(select(func.count()).select_from(Report).where(Report.owner_user_id == ctx.owner_id))
        read = db.scalar(select(func.count()).select_from(ReportRead).join(Report, Report.id == ReportRead.report_id)
                         .where(ReportRead.user_id == ctx.user.id, Report.owner_user_id == ctx.owner_id))
        unread = (total or 0) - (read or 0)
    return {"basins": [{k: b[k] for k in ("id", "name", "species", "species_name", "status", "live", "cls", "sat",
                                          "risk", "capacity", "fish", "density", "thr", "sensors")} for b in basins],
            "alerts": alerts[:5], "open_alerts": len(alerts), "unread_reports": unread,
            "simulator": {"paused": _sim_paused(db, ctx)}, "server_time": datetime.now(UTC).isoformat()}


@router.get("/overview")
def overview(ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    basins = live_basins(db, ctx.owner_id, with_finance=True)
    alerts = alerts_for(db, ctx.owner_id, resolved=False)
    people = br.team(db, ctx.owner_id)
    rev = sum(b["finance"]["revenue"] for b in basins)
    costs = sum(b["finance"]["costs"] for b in basins)
    feed = sum(b["finance"]["feed"] for b in basins)
    summary = br.owner_summary(db, ctx.owner_id, now) if basins else {"text": "", "actions": []}
    return {
        "basins": basins,
        "alerts": {"open": len(alerts), "sensor": sum(a["kind"] == "sensor" for a in alerts),
                   "water": sum(a["kind"] == "water" for a in alerts)},
        "finance": {"revenue": rev, "costs": costs, "profit": rev - costs,
                    "margin": (rev - costs) / rev if rev else 0, "feed_share": feed / costs if costs else 0},
        "team": {"total": len(people), "workers": sum(p["role"] == "worker" for p in people),
                 "technicians": sum(p["role"] == "technician" for p in people)},
        "summary": summary["text"], "actions": summary["actions"],
    }


@router.get("/today")
def today(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    """Home screen of workers (Today) and technicians (Today)."""
    now = datetime.now(UTC)
    tz = br.farm_tz(db, ctx.owner_id)
    basins = live_basins(db, ctx.owner_id)
    kind = role_alert_kind(ctx.role)
    rel = alerts_for(db, ctx.owner_id, resolved=False, kind=kind) if ctx.can("alerts") else []
    out = {"healthy": sum(b["status"] == "healthy" for b in basins), "basin_count": len(basins),
           "alerts": rel, "high": sum(SEV_RANK[a["severity"]] >= 3 for a in rel),
           "basins": basins if ctx.can("basins") else []}
    if ctx.role == "worker" or ctx.is_owner:
        out["hero_text"] = br.worker_hero_text(rel, {b["id"]: b for b in basins}, tz, now)
        out["tasks"] = br.tasks_json(db, ctx.owner_id, assignee=ctx.user.id)
        lows = br.overnight_lows(db, ctx.owner_id, now)
        out["overnight_low"] = br.worst_overnight_low(lows)
    if ctx.role == "technician" or ctx.is_owner:
        sensors = db.scalars(select(Sensor).where(Sensor.owner_user_id == ctx.owner_id).order_by(Sensor.code)).all()
        names = {b["id"]: b["name"] for b in basins}
        out["probes"] = {"total": len(sensors),
                         "bad": [{"code": s.code, "basin": names.get(str(s.basin_id), ""), "health": s.health}
                                 for s in sensors if s.health != "ok"]}
        out["open_tasks"] = br.tasks_json(db, ctx.owner_id, open_only=True)
        lc = br.last_calibration(db, ctx.owner_id)
        out["last_calibration"] = lc.isoformat() if lc else None
    return out


@router.get("/public/showcase")
def showcase(db: Session = Depends(get_db)):
    """Public data for the website: live readings and the Basin 3 oxygen curve of the demo farm."""
    from ..models import User
    from ..services.views import basins_with_sensors, overnight_low, series_24h

    owner = db.scalar(select(User).where(User.email == "nadia@lacvert.farm"))
    if not owner:
        return {"available": False}
    bs = {b.name: s for b, s in basins_with_sensors(db, owner.id)}

    def val(basin: str, m: str):
        s = bs.get(basin, {}).get(m)
        return s.last_value if s else None

    out = {"available": True, "do": val("Basin 3", "do"), "temp": val("Basin 1", "temp"), "ph": val("Basin 2", "ph")}
    s3 = bs.get("Basin 3", {}).get("do")
    if s3:
        series = series_24h(db, s3)
        out["series"] = series
        out["low"] = overnight_low(series)
        out["warn"] = s3.min_value
    return out


@router.get("/simulator")
def simulator_state(ctx: Ctx = Depends(current_ctx), db: Session = Depends(get_db)):
    return {"paused": _sim_paused(db, ctx)}


def _set_sim(db: Session, ctx: Ctx, paused: bool):
    st = db.get(SimulatorState, ctx.owner_id) or SimulatorState(owner_user_id=ctx.owner_id)
    st.paused = paused
    db.add(st)
    notify(db, {"type": "simulator", "owner_id": str(ctx.owner_id), "paused": paused})
    db.commit()
    return {"paused": paused}


@router.post("/simulator/pause")
def pause(ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    return _set_sim(db, ctx, True)


@router.post("/simulator/resume")
def resume(ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    return _set_sim(db, ctx, False)


@router.post("/demo/load")
def demo_load(ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    if db.scalar(select(func.count()).select_from(Basin).where(Basin.owner_user_id == ctx.owner_id)):
        raise HTTPException(409, "Your farm already has basins. The demo can only be loaded into an empty farm.")
    if db.scalar(select(func.count()).select_from(UserRole).where(UserRole.owner_user_id == ctx.owner_id,
                                                                  UserRole.role != "owner")):
        raise HTTPException(409, "Your farm already has team members. The demo can only be loaded into an empty farm.")
    load_demo(db, ctx.owner_id)
    notify(db, {"type": "farm", "owner_id": str(ctx.owner_id), "action": "demo_loaded"})
    db.commit()
    return {"ok": True}
