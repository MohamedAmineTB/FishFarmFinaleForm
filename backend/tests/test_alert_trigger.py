"""The SQL alert engine (trigger on readings) and the alert / report / task workflows."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.db import session_scope


def _sensor(db, owner_email: str, basin: str, typ: str):
    return db.execute(
        text(
            "SELECT s.id, s.basin_id FROM sensors s JOIN basins b ON b.id = s.basin_id "
            "JOIN users u ON u.id = s.owner_user_id WHERE u.email = :e AND b.name = :b AND s.type = :t"
        ),
        {"e": owner_email, "b": basin, "t": typ},
    ).first()


def test_out_of_range_reading_opens_one_alert(client, other_owner_h):
    with session_scope() as db:
        sid, bid = _sensor(db, "omar@other.farm", "Pond A", "oxygen")
        owner = db.execute(text("SELECT owner_user_id FROM sensors WHERE id = :s"), {"s": sid}).scalar()
        now = datetime.now(UTC)
        db.execute(
            text("INSERT INTO readings (owner_user_id, sensor_id, value, recorded_at) VALUES (:o, :s, 7.2, :t)"),
            {"o": owner, "s": sid, "t": now},
        )
        assert db.execute(text("SELECT count(*) FROM alerts WHERE sensor_id = :s"), {"s": sid}).scalar() == 0
        # carp warning level is 5 mg/L, critical 3
        for i, v in enumerate((4.4, 4.1), start=1):
            db.execute(
                text("INSERT INTO readings (owner_user_id, sensor_id, value, recorded_at) VALUES (:o, :s, :v, :t)"),
                {"o": owner, "s": sid, "v": v, "t": now + timedelta(seconds=6 * i)},
            )
        rows = db.execute(text("SELECT title, description, severity, kind FROM alerts WHERE sensor_id = :s"), {"s": sid}).all()
        assert len(rows) == 1, "one open alert per sensor"
        title, descr, sev, kind = rows[0]
        assert title == "Oxygen below 5.0 mg/L" and kind == "water"
        assert "4.40 mg/L" in descr and "common carp" in descr
        assert sev == "medium"
        assert db.execute(text("SELECT last_value FROM sensors WHERE id = :s"), {"s": sid}).scalar() == 4.1
        assert db.execute(text("SELECT status FROM basins WHERE id = :b"), {"b": bid}).scalar() == "warning"
        # below the critical level -> critical alert once the first is resolved
        db.execute(text("UPDATE alerts SET is_resolved = true WHERE sensor_id = :s"), {"s": sid})
        db.execute(
            text("INSERT INTO readings (owner_user_id, sensor_id, value, recorded_at) VALUES (:o, :s, 2.5, :t)"),
            {"o": owner, "s": sid, "t": now + timedelta(seconds=30)},
        )
        sev = db.execute(text("SELECT severity FROM alerts WHERE sensor_id = :s AND NOT is_resolved"), {"s": sid}).scalar()
        assert sev == "critical"
        assert db.execute(text("SELECT status FROM basins WHERE id = :b"), {"b": bid}).scalar() == "critical"


def test_bulk_load_skips_engine(client):
    with session_scope() as db:
        sid, _ = _sensor(db, "omar@other.farm", "Pond A", "ph")
        owner = db.execute(text("SELECT owner_user_id FROM sensors WHERE id = :s"), {"s": sid}).scalar()
        db.execute(text("SET LOCAL app.bulk_load = 'on'"))
        db.execute(
            text("INSERT INTO readings (owner_user_id, sensor_id, value, recorded_at) VALUES (:o, :s, 11, now())"),
            {"o": owner, "s": sid},
        )
        assert db.execute(text("SELECT count(*) FROM alerts WHERE sensor_id = :s"), {"s": sid}).scalar() == 0


def test_demo_alerts_match_prototype(client, owner_h):
    alerts = client.get("/api/alerts", headers=owner_h).json()
    titles = [a["title"] for a in alerts]
    assert "Oxygen below 7.0 mg/L" in titles
    assert "pH above 8.5" in titles
    assert "Temperature probe not changing" in titles
    # most severe first
    sev = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    assert [sev[a["severity"]] for a in alerts] == sorted((sev[a["severity"]] for a in alerts), reverse=True)


def test_resolve_and_reopen(client, owner_h, worker_h):
    a = next(x for x in client.get("/api/alerts", headers=worker_h).json() if x["metric"] == "ph")
    assert client.post(f"/api/alerts/{a['id']}/resolve", headers=worker_h, json={"note": ""}).status_code == 422
    r = client.post(f"/api/alerts/{a['id']}/resolve", headers=worker_h, json={"note": "Tested ammonia, all fine"})
    assert r.status_code == 200
    body = r.json()
    assert body["resolved"] and body["by"] == "Karim Benali" and body["note"] == "Tested ammonia, all fine"
    done = client.get("/api/alerts?status=resolved", headers=owner_h).json()
    assert any(x["id"] == a["id"] for x in done)
    r = client.post(f"/api/alerts/{a['id']}/reopen", headers=owner_h)
    assert r.status_code == 200 and not r.json()["resolved"] and r.json()["note"] is None


def test_reports_read_state(client, owner_h, worker_h):
    r = client.post("/api/reports", headers=worker_h, json={"title": "", "body": "x"})
    assert r.status_code == 422
    r = client.post("/api/reports", headers=worker_h, json={"title": "Test shift", "body": "All good"})
    assert r.status_code == 201
    inbox = client.get("/api/reports", headers=owner_h).json()
    new = next(x for x in inbox if x["title"] == "Test shift")
    assert not new["read"] and new["author"] == "Karim Benali" and new["role"] == "Worker"
    assert client.post(f"/api/reports/{new['id']}/read", headers=owner_h).json()["read"]
    assert client.delete(f"/api/reports/{new['id']}/read", headers=owner_h).json()["read"] is False
    client.post("/api/reports/read-all", headers=owner_h)
    assert all(x["read"] for x in client.get("/api/reports", headers=owner_h).json())
    assert client.get("/api/live", headers=owner_h).json()["unread_reports"] == 0


def test_maintenance_log_creates_report_and_task(client, owner_h, tech_h):
    sensors = client.get("/api/sensors", headers=tech_h).json()
    assert len(sensors) == 12 and any(s["health"] == "stuck" for s in sensors)
    s = next(x for x in sensors if x["code"] == "S-05")
    r = client.post(
        "/api/maintenance",
        headers=tech_h,
        json={"sensor_id": s["id"], "work_type": "Calibration", "due_date": "2026-12-01", "description": "Buffer 7/10"},
    )
    assert r.status_code == 201
    titles = [x["title"] for x in client.get("/api/reports", headers=owner_h).json()]
    assert "Calibration, S-05 · Basin 2 · pH" in titles
    tasks = client.get("/api/tasks?scope=all", headers=tech_h).json()
    t = next(x for x in tasks if x["title"] == "Calibration: S-05 · Basin 2 · pH")
    assert client.patch(f"/api/tasks/{t['id']}", headers=tech_h, json={"status": "in progress"}).json()["status"] == "in_progress"


def test_overview_and_today(client, owner_h, worker_h, tech_h):
    ov = client.get("/api/overview", headers=owner_h).json()
    assert ov["finance"]["revenue"] == 77000 and ov["finance"]["costs"] == 49000
    assert ov["team"]["workers"] >= 3 and len(ov["actions"]) == 3
    assert ov["actions"][0]["title"] == "Cut the Basin 3 evening feed by a third"
    t = client.get("/api/today", headers=worker_h).json()
    assert any(task["title"] == "Clean aerator diffusers, Basin 3" for task in t["tasks"])
    assert t["overnight_low"]["basin"] == "Basin 3"
    tt = client.get("/api/today", headers=tech_h).json()
    assert tt["probes"]["total"] == 12
