"""Demo farm "Lac Vert", as in the approved prototype.

Used by `python -m app.seed` (the public demo accounts) and by the "Load demo farm"
button of a new owner (same basins and history, demo team with farm-specific emails).
"""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import Basin, Owner, Report, ReportRead, Sensor, Task, User
from ..pipeline.backfill import backfill_owner
from ..pipeline.health import run_health
from .farm import create_basin, create_member

BASINS = [
    # name, species, m3, fish, revenue, feed, maint, ops, profile
    (
        "Basin 1",
        "tilapia",
        180,
        4200,
        21400,
        9100,
        1300,
        2600,
        {"base": {"temp": 28.2, "do": 7.2, "ph": 7.35}, "amp": {"temp": 0.8, "do": 1.5, "ph": 0.3}},
    ),
    (
        "Basin 2",
        "tilapia",
        160,
        3800,
        18200,
        8700,
        1100,
        2400,
        {"base": {"temp": 28.6, "do": 7.0, "ph": 8.22}, "amp": {"temp": 0.9, "do": 1.5, "ph": 0.3}},
    ),
    (
        "Basin 3",
        "rainbow_trout",
        140,
        2600,
        24800,
        9800,
        1900,
        3100,
        {
            "base": {"temp": 17.6, "do": 7.3, "ph": 7.2},
            "amp": {"temp": 0.6, "do": 1.45, "ph": 0.2},
            "night_dip": {"from": 2.8, "to": 5.6, "depth": 0.28},
        },
    ),
    (
        "Basin 4",
        "common_carp",
        200,
        3100,
        12600,
        5900,
        900,
        2200,
        {"base": {"temp": 26.1, "do": 7.0, "ph": 7.6}, "amp": {"temp": 1.0, "do": 1.7, "ph": 0.3}},
    ),
]

TEAM = [
    ("Karim Benali", "karim", "worker", "06:00", "14:00"),
    ("Léa Martin", "lea", "worker", "14:00", "22:00"),
    ("Inès Haddad", "ines", "worker", "22:00", "06:00"),
    ("Samir Touati", "samir", "technician", "08:00", "17:00"),
]

REPORTS = [
    (
        "karim",
        "shift",
        3.2,
        "Morning shift: Basin 3 fish slow at feeding",
        "Trout in Basin 3 came up slowly at the 07:00 feed and left about a fifth of the ration. Water looked clear. "
        "I ran the aerator for an extra hour and will watch the evening feed.",
        "Basin 3",
    ),
    (
        "samir",
        "maintenance",
        20,
        "Replaced pH probe, Basin 1",
        "Old probe drifted +0.2 against the buffer solution. New probe installed and calibrated at pH 7 and pH 10. "
        "Next calibration due in 30 days.",
        "Basin 1",
    ),
    (
        "ines",
        "shift",
        26,
        "Night shift: all basins normal",
        "Checked all four basins at 01:00 and 04:00. Aerators running in Basins 2 and 3. No dead fish found.",
        None,
    ),
    (
        "samir",
        "maintenance",
        50,
        "Aerator bearing noise, Basin 3",
        "Aerator in Basin 3 makes a grinding noise at start-up. Bearing ordered, arrives Thursday. Aerator still works.",
        "Basin 3",
    ),
]

# days ago of the last calibration per probe, following the prototype's pattern (12 Oct, 28 Oct, 2 Nov, 9 Nov)
CAL_DAYS = [38, 22, 17, 10]


def load_demo(
    db: Session, owner_id: uuid.UUID, *, team_emails: str = "farm", password: str = "demo1234", now: datetime | None = None
) -> None:
    """Fill an (empty) farm with the demo basins, 30 days of history, team, reports, tasks and alerts.

    team_emails="public" uses the published demo addresses (karim@lacvert.farm …);
    otherwise addresses are made unique for this farm.
    """
    now = (now or datetime.now(UTC)).replace(microsecond=0)
    owner = db.get(Owner, owner_id)
    tz = ZoneInfo(owner.timezone)
    suffix = uuid.uuid4().hex[:6]

    # team
    users: dict[str, User] = {}
    for name, key, role, s, e in TEAM:
        email = f"{key}@lacvert.farm" if team_emails == "public" else f"{key}.{suffix}@demo.lacvert.farm"
        users[key] = create_member(db, owner_id, name=name, email=email, password=password, role=role, shift_start=s, shift_end=e)

    # basins + probes
    basins: dict[str, Basin] = {}
    k = 0
    for name, sp, cap, fish, rev, feed, maint, ops, prof in BASINS:
        cal = []
        for _ in range(3):
            k += 1
            cal.append(now - timedelta(days=CAL_DAYS[(k + 1) % 4]))
        basins[name] = create_basin(
            db,
            owner_id,
            name=name,
            species=sp,
            capacity=cap,
            fish_count=fish,
            revenue=rev,
            feed=feed,
            maint=maint,
            ops=ops,
            profile=prof,
            calibrated=cal,
        )
    sensors = {(s.basin_id, s.type): s for s in db.scalars(select(Sensor).where(Sensor.owner_user_id == owner_id))}

    # injected probe faults: Basin 4 temperature stuck at 26.0 °C for 3 h 15 min, Basin 2 pH drifting upwards
    sensors[(basins["Basin 4"].id, "temperature")].sim_fault = {
        "type": "stuck",
        "value": 26.0,
        "since": (now - timedelta(hours=3, minutes=15)).isoformat(),
    }
    sensors[(basins["Basin 2"].id, "ph")].sim_fault = {
        "type": "drift",
        "rate_per_h": 0.006,
        "max": 0.15,
        "since": (now - timedelta(hours=30)).isoformat(),
    }
    db.flush()

    backfill_owner(db, owner_id, days=30, step_minutes=5, end=now)

    # water alerts from the last 24 h, raised by the real alert engine (same text and severity rules)
    day_ago = now - timedelta(hours=24)
    for basin, typ, order in (("Basin 2", "ph", "DESC"), ("Basin 3", "oxygen", "ASC")):
        s = sensors[(basins[basin].id, typ)]
        row = db.execute(
            text(
                f"SELECT value, recorded_at FROM readings WHERE sensor_id = :s AND recorded_at > :a "
                f"ORDER BY value {order} LIMIT 1"
            ),
            {"s": s.id, "a": day_ago},
        ).first()
        if row:
            db.execute(text("SELECT ff_evaluate_reading(:s, :v, :t)"), {"s": s.id, "v": row[0], "t": row[1]})
    # the stuck probe is found by the sensor-health job, like in production
    run_health(db, owner_id=owner_id, now=now)

    # reports (the owner has already read all but the newest)
    for i, (author, kind, hrs, title, body, basin) in enumerate(REPORTS):
        r = Report(
            owner_user_id=owner_id,
            author_user_id=users[author].id,
            kind=kind,
            title=title,
            body=body,
            basin_id=basins[basin].id if basin else None,
            generated_at=now - timedelta(hours=hrs),
        )
        db.add(r)
        db.flush()
        if i > 0:
            db.add(ReportRead(report_id=r.id, user_id=owner_id, read_at=now - timedelta(hours=hrs - 1)))

    today = now.astimezone(tz).date()
    db.add(
        Task(
            owner_user_id=owner_id,
            title="Recalibrate pH probe, Basin 2",
            assignee_user_id=users["samir"].id,
            basin_id=basins["Basin 2"].id,
            sensor_id=sensors[(basins["Basin 2"].id, "ph")].id,
            status="pending",
            source="maintenance",
            due_date=today + timedelta(days=1),
            created_by=owner_id,
            created_at=now - timedelta(hours=4),
        )
    )
    db.add(
        Task(
            owner_user_id=owner_id,
            title="Clean aerator diffusers, Basin 3",
            assignee_user_id=users["karim"].id,
            basin_id=basins["Basin 3"].id,
            status="in_progress",
            source="manual",
            due_date=today,
            created_by=owner_id,
            created_at=now - timedelta(hours=5),
        )
    )
    db.flush()
    for b in basins.values():
        db.execute(text("SELECT ff_refresh_basin_status(:b)"), {"b": b.id})
