"""Daily briefing: the owner's "Today's actions", the home-screen summaries and the worker/technician days.

Everything here is deterministic and computed from the database (open alerts, probe
health, ML predictions, shifts). The assistant reads the same briefing through the
`get_farm_briefing` tool; it never invents it.
"""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import SPECIES_NAMES
from ..models import Owner, Sensor, Task, User, UserRole
from .views import alerts_for, basins_with_sensors, live_basins, overnight_low, series_24h

SPECIES_SHORT = {"tilapia": "tilapia", "rainbow_trout": "trout", "common_carp": "carp", "sea_bass": "sea bass",
                 "sea_bream": "sea bream", "atlantic_salmon": "salmon"}
METRIC_WORD = {"temperature": "temperature", "ph": "pH", "oxygen": "oxygen"}


def farm_tz(db: Session, owner_id: uuid.UUID) -> ZoneInfo:
    o = db.get(Owner, owner_id)
    return ZoneInfo(o.timezone if o else "Europe/Paris")


def when_phrase(iso: str, tz: ZoneInfo, now: datetime) -> str:
    """'last night' for a time between 20:00 and 08:00 within the last 18 h, else 'at HH:MM' / 'yesterday'."""
    t = datetime.fromisoformat(iso)
    lt = t.astimezone(tz)
    if now - t < timedelta(hours=18) and (lt.hour >= 20 or lt.hour < 8):
        return "last night"
    if lt.date() == now.astimezone(tz).date():
        return f"at {lt:%H:%M}"
    return "yesterday" if (now.astimezone(tz).date() - lt.date()).days == 1 else f"on {lt:%d %b}"


def _hours(hhmm: str) -> float:
    h, m = hhmm.split(":")
    return int(h) + int(m) / 60


def on_shift_at(start: str, end: str, hour: float) -> bool:
    s, e = _hours(start), _hours(end)
    length = (e - s + 24) % 24 or 24
    return (hour - s + 24) % 24 < length


def team(db: Session, owner_id: uuid.UUID) -> list[dict]:
    rows = db.execute(select(User, UserRole).join(UserRole, UserRole.user_id == User.id)
                      .where(UserRole.owner_user_id == owner_id, UserRole.role != "owner")
                      .order_by(UserRole.created_at, User.name)).all()
    return [{"id": str(u.id), "name": u.name, "email": u.email, "role": r.role, "shift_start": r.shift_start,
             "shift_end": r.shift_end, "permissions": r.permissions} for u, r in rows]


def overnight_lows(db: Session, owner_id: uuid.UUID, now: datetime) -> dict[str, dict]:
    """Lowest oxygen of the last 24 h per basin, with the species warning level for comparison."""
    from ..domain import load_thresholds

    th = load_thresholds(db)
    out = {}
    for b, sensors in basins_with_sensors(db, owner_id):
        s = sensors.get("do")
        if s:
            low = overnight_low(series_24h(db, s, now))
            if low:
                out[str(b.id)] = {**low, "basin": b.name, "warn": th[b.species].do_warn}
    return out


def worst_overnight_low(lows: dict[str, dict]) -> dict | None:
    """The basin whose night low went furthest under its own species warning level."""
    if not lows:
        return None
    return min(lows.values(), key=lambda x: x["value"] - (x["warn"] or 0))


def most_urgent_water(alerts: list[dict], tz: ZoneInfo, now: datetime) -> dict | None:
    water = [a for a in alerts if a["kind"] == "water" and not a["resolved"]]
    return water[0] if water else None


def urgent_sentence(a: dict, tz: ZoneInfo, now: datetime) -> str:
    """'Basin 3 oxygen fell to 5.2 mg/L last night.'"""
    when = when_phrase(a["time"], tz, now)
    if a["metric"] == "do":
        return f"{a['basin']} oxygen fell to {a['value']:.1f} mg/L {when}."
    if a["metric"] == "ph":
        verb = "rose to" if a["type"] == "above_range" else "fell to"
        return f"{a['basin']} pH {verb} {a['value']:.2f} {when}."
    verb = "rose to" if a["type"] == "above_range" else "fell to"
    return f"{a['basin']} temperature {verb} {a['value']:.1f} °C {when}."


def owner_actions(db: Session, owner_id: uuid.UUID, now: datetime | None = None) -> list[dict]:
    """Today's 3 actions, in order of urgency."""
    now = now or datetime.now(UTC)
    tz = farm_tz(db, owner_id)
    basins = live_basins(db, owner_id)
    alerts = alerts_for(db, owner_id, resolved=False)
    people = team(db, owner_id)
    acts: list[dict] = []

    # 1-2: the basin with the highest predicted (or observed) night oxygen risk
    def o2_alert(b):
        return next((a for a in alerts if a["basin_id"] == b["id"] and a["metric"] == "do" and a["kind"] == "water"), None)

    risky = sorted(basins, key=lambda b: (b["risk"] or 0) + (0.5 if o2_alert(b) else 0), reverse=True)
    rb = risky[0] if risky and ((risky[0]["risk"] or 0) >= 0.3 or o2_alert(risky[0])) else None
    if rb:
        if rb["risk"] is not None:
            sub = f"18:00 · {round(rb['risk'] * 100)}% chance of another oxygen dip before dawn (estimate)"
        else:
            a = o2_alert(rb)
            sub = f"18:00 · oxygen fell to {a['value']:.1f} mg/L {when_phrase(a['time'], tz, now)}"
        acts.append({"time": "18:00", "title": f"Cut the {rb['name']} evening feed by a third", "text": sub,
                     "action": {"type": "ask", "q": f"Why did oxygen drop in {rb['name']} last night?"}})
        night = next((p for p in people if p["role"] == "worker" and p["shift_start"]
                      and on_shift_at(p["shift_start"], p["shift_end"], 23)), None)
        acts.append({"time": "22:00", "title": f"Run the {rb['name']} aerator until sunrise",
                     "text": "22:00 · " + (f"night worker {night['name']}" if night else "whoever is on the night shift"),
                     "action": {"type": "open-basin", "id": rb["id"]}})

    # 3: a broken probe goes to the technician
    for a in alerts:
        if a["kind"] == "sensor":
            tech = next((p for p in people if p["role"] == "technician"), None)
            what = METRIC_WORD.get({"do": "oxygen", "temp": "temperature", "ph": "ph"}.get(a["metric"], ""), "")
            val = f"stuck at {a['value']:.1f} °C" if a["metric"] == "temp" and a["value"] is not None else a["title"].lower()
            acts.append({"time": "today", "title": f"Check the {a['basin']} {what} probe",
                         "text": f"today · {val}" + (f", {tech['name']}" if tech else ""),
                         "action": {"type": "ask", "q": f"Is the {a['basin']} alert a sensor problem?"}})
            break

    # other open water alerts, then routine
    for a in alerts:
        if len(acts) >= 3:
            break
        if a["kind"] == "water" and not (rb and a["basin_id"] == rb["id"] and a["metric"] == "do"):
            what = {"ph": "pH", "temp": "temperature", "do": "oxygen"}[a["metric"]]
            acts.append({"time": "15:00" if a["metric"] == "ph" else "today",
                         "title": f"Re-check the {a['basin']} {what}",
                         "text": f"{'15:00' if a['metric'] == 'ph' else 'today'} · {a['title']} ({a['severity']})",
                         "action": {"type": "ask", "q": f"Explain alert {a['id']}"}})
    if len(acts) < 3:
        acts.append({"time": "today", "title": "Walk the basins and read the shift reports",
                     "text": "today · no other open problems", "action": {"type": "nav", "view": "reports"}})
    return acts[:3]


def owner_summary(db: Session, owner_id: uuid.UUID, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    tz = farm_tz(db, owner_id)
    alerts = alerts_for(db, owner_id, resolved=False)
    urgent = most_urgent_water(alerts, tz, now) or (alerts[0] if alerts else None)
    if not alerts:
        text_ = "No open alerts. The alert engine keeps checking every basin."
    else:
        n = len(alerts)
        text_ = f"{n} open alert{'' if n == 1 else 's'}."
        if urgent and urgent["kind"] == "water":
            text_ += " The most urgent: " + urgent_sentence(urgent, tz, now)
        elif urgent:
            text_ += f" The most urgent: {urgent['basin']} · {urgent['title'].lower()}."
    return {"text": text_, "actions": owner_actions(db, owner_id, now)}


def worker_hero_text(alerts: list[dict], basins: dict[str, dict], tz: ZoneInfo, now: datetime) -> str:
    water = [a for a in alerts if a["kind"] == "water" and not a["resolved"]]
    if not water:
        return "No water alerts open. Walk the basins and note anything unusual in your shift report."
    n = len(water)
    a = water[0]
    sp = SPECIES_SHORT.get(basins.get(a["basin_id"], {}).get("species", ""), "fish")
    when = when_phrase(a["time"], tz, now)
    if a["metric"] == "do":
        start = f"oxygen fell under the {sp} warning level {when}"
    elif a["metric"] == "ph":
        start = f"pH went outside the {sp} safe range {when}"
    else:
        start = f"temperature went outside the {sp} safe range {when}"
    return f"{n} water alert{'s' if n > 1 else ''} open. Start with {a['basin']}: {start}."


def tasks_json(db: Session, owner_id: uuid.UUID, *, assignee: uuid.UUID | None = None,
               open_only: bool = False) -> list[dict]:
    q = select(Task).where(Task.owner_user_id == owner_id)
    if assignee:
        q = q.where(Task.assignee_user_id == assignee)
    if open_only:
        q = q.where(Task.status != "fixed")
    rows = db.scalars(q.order_by(Task.created_at.desc())).all()
    names = {u.id: u.name for u in db.scalars(select(User).where(User.id.in_({t.assignee_user_id for t in rows})))}
    tz = farm_tz(db, owner_id)
    today = datetime.now(UTC).astimezone(tz).date()

    def due(t: Task) -> str:
        if t.due_label:
            return t.due_label
        if not t.due_date:
            return "no date"
        d = (t.due_date - today).days
        return "Today" if d == 0 else "Tomorrow" if d == 1 else "Yesterday" if d == -1 else f"{t.due_date:%d %b}"

    return [{"id": str(t.id), "title": t.title, "who": names.get(t.assignee_user_id, "Unassigned"),
             "assignee_id": str(t.assignee_user_id) if t.assignee_user_id else None, "due": due(t),
             "due_date": t.due_date.isoformat() if t.due_date else None, "status": t.status, "source": t.source}
            for t in rows]


def last_calibration(db: Session, owner_id: uuid.UUID) -> datetime | None:
    return max((s.last_calibrated_at for s in db.scalars(select(Sensor).where(Sensor.owner_user_id == owner_id))
                if s.last_calibrated_at), default=None)


def species_name(code: str) -> str:
    return SPECIES_NAMES.get(code, code)


