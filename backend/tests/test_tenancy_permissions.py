"""Multi-tenancy (owner A can't see owner B) and server-side permissions (403)."""


def test_owner_b_cannot_see_owner_a(client, owner_h, other_owner_h):
    a_basins = client.get("/api/basins", headers=owner_h).json()
    b_basins = client.get("/api/basins", headers=other_owner_h).json()
    assert {b["name"] for b in a_basins} == {"Basin 1", "Basin 2", "Basin 3", "Basin 4"}
    assert [b["name"] for b in b_basins] == ["Pond A"]
    a_id = a_basins[0]["id"]
    # direct access to another farm's basin looks like it does not exist
    assert client.get(f"/api/basins/{a_id}", headers=other_owner_h).status_code == 404
    assert client.get(f"/api/basins/{a_id}/readings", headers=other_owner_h).status_code == 404
    assert client.put(f"/api/basins/{a_id}/finances", headers=other_owner_h,
                      json={"fish": 1, "feed": 1, "maint": 1, "ops": 1}).status_code == 404
    # alerts, reports, team are scoped too
    assert all(a["basin"] == "Pond A" for a in client.get("/api/alerts", headers=other_owner_h).json())
    assert client.get("/api/reports", headers=other_owner_h).json() == []
    alert_id = client.get("/api/alerts", headers=owner_h).json()[0]["id"]
    assert client.post(f"/api/alerts/{alert_id}/resolve", headers=other_owner_h,
                       json={"note": "x"}).status_code == 404


def test_owner_only_endpoints_reject_team(client, worker_h, tech_h):
    for h in (worker_h, tech_h):
        assert client.get("/api/team", headers=h).status_code == 403
        assert client.get("/api/overview", headers=h).status_code == 403
        assert client.get("/api/reports", headers=h).status_code == 403
        assert client.post("/api/simulator/pause", headers=h).status_code == 403


def test_permission_switch_is_enforced(client, owner_h, worker_h):
    team = client.get("/api/team", headers=owner_h).json()
    karim = next(t for t in team if t["email"] == "karim@lacvert.farm")
    assert client.get("/api/alerts", headers=worker_h).status_code == 200
    r = client.patch(f"/api/team/{karim['id']}/permissions", headers=owner_h, json={"permissions": {"alerts": False}})
    assert r.status_code == 200 and r.json()["permissions"]["alerts"] is False
    assert client.get("/api/alerts", headers=worker_h).status_code == 403
    client.patch(f"/api/team/{karim['id']}/permissions", headers=owner_h, json={"permissions": {"alerts": True}})
    assert client.get("/api/alerts", headers=worker_h).status_code == 200
    # unknown permission keys are refused
    assert client.patch(f"/api/team/{karim['id']}/permissions", headers=owner_h,
                        json={"permissions": {"admin": True}}).status_code == 422


def test_role_scoped_alerts(client, owner_h, worker_h, tech_h):
    everything = client.get("/api/alerts", headers=owner_h).json()
    water = client.get("/api/alerts", headers=worker_h).json()
    hardware = client.get("/api/alerts", headers=tech_h).json()
    assert all(a["kind"] == "water" for a in water)
    assert all(a["kind"] == "sensor" for a in hardware)
    assert len(everything) == len(water) + len(hardware)
    # a worker cannot resolve a hardware alert
    assert client.post(f"/api/alerts/{hardware[0]['id']}/resolve", headers=worker_h,
                       json={"note": "x"}).status_code == 404


def test_add_member_can_sign_in(client, owner_h):
    r = client.post("/api/team", headers=owner_h, json={"name": "Yasmine Test", "email": "yasmine@lacvert.farm",
                                                          "password": "farm-1234", "role": "worker",
                                                          "shift_start": "06:00", "shift_end": "14:00"})
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/login", json={"email": "yasmine@lacvert.farm", "password": "farm-1234",
                                             "portal": "team"})
    assert r.status_code == 200 and r.json()["role"] == "worker"
    dup = client.post("/api/team", headers=owner_h, json={"name": "Again", "email": "yasmine@lacvert.farm",
                                                            "password": "farm-1234", "role": "worker",
                                                            "shift_start": "06:00", "shift_end": "14:00"})
    assert dup.status_code == 409
