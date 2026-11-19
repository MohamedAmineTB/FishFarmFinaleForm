from tests.conftest import login


def test_register_validates_input(client):
    r = client.post(
        "/api/auth/register",
        json={"name": "A", "email": "not-an-email", "password": "short", "farm": "F", "company": "C", "country": "France"},
    )
    assert r.status_code == 422


def test_register_duplicate_email(client):
    r = client.post(
        "/api/auth/register",
        json={
            "name": "X",
            "email": "nadia@lacvert.farm",
            "password": "longenough1",
            "farm": "F",
            "company": "C",
            "country": "France",
        },
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "email_taken"


def test_new_owner_gets_empty_farm(client):
    r = client.post(
        "/api/auth/register",
        json={
            "name": "Lina New",
            "email": "lina@new.farm",
            "password": "longenough1",
            "farm": "New Farm",
            "company": "NewCo",
            "country": "France",
        },
    )
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = client.get("/api/me", headers=h).json()
    assert me["role"] == "owner" and me["farm"]["name"] == "New Farm"
    assert client.get("/api/basins", headers=h).json() == []
    assert client.get("/api/team", headers=h).json() == []


def test_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "nadia@lacvert.farm", "password": "nope", "portal": "owner"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "bad_credentials"


def test_wrong_portal(client):
    r = client.post("/api/auth/login", json={"email": "karim@lacvert.farm", "password": "demo1234", "portal": "owner"})
    assert r.status_code == 403 and r.json()["detail"]["role"] == "worker"
    r = client.post("/api/auth/login", json={"email": "nadia@lacvert.farm", "password": "demo1234", "portal": "team"})
    assert r.status_code == 403 and r.json()["detail"]["role"] == "owner"


def test_protected_needs_token(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_refresh_rotates_and_logout_revokes(client):
    login(client, "nadia@lacvert.farm")
    old = client.cookies.get("ff_refresh")
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200 and r.json()["access_token"]
    new = client.cookies.get("ff_refresh")
    assert new and new != old

    def only(cookie):
        client.cookies.clear()
        client.cookies.set("ff_refresh", cookie)

    only(old)  # the old refresh token was rotated out
    assert client.post("/api/auth/refresh").status_code == 401
    only(new)
    assert client.post("/api/auth/logout").status_code == 200
    only(new)  # signing out revokes it
    assert client.post("/api/auth/refresh").status_code == 401
    client.cookies.clear()
