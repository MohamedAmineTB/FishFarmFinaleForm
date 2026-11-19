"""Test setup: a separate database migrated from scratch, a demo farm and a second, empty farm."""

import os

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5433/fishfarm_test")
os.environ["DATABASE_URL"] = TEST_DB
os.environ.setdefault("JWT_SECRET", "test-secret-0123456789-0123456789-abcdef")
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_BACKEND"] = "hash"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _reset_schema() -> None:
    eng = create_engine(TEST_DB, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        c.execute(text("DROP SCHEMA IF EXISTS ai CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    eng.dispose()
    cfg = Config(os.path.join(HERE, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def database():
    _reset_schema()
    from app.seed import main as seed

    seed()
    yield


@pytest.fixture(scope="session")
def client(database):
    from app.main import app

    with TestClient(app) as c:
        yield c


def login(client, email: str, portal: str = "owner", password: str = "demo1234") -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password, "portal": portal})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def owner_h(client):
    return login(client, "nadia@lacvert.farm")


@pytest.fixture(scope="session")
def worker_h(client):
    return login(client, "karim@lacvert.farm", "team")


@pytest.fixture(scope="session")
def tech_h(client):
    return login(client, "samir@lacvert.farm", "team")


@pytest.fixture(scope="session")
def other_owner_h(client):
    r = client.post("/api/auth/register", json={"name": "Omar Other", "email": "omar@other.farm",
                                                 "password": "secret-pass-1", "farm": "Other Farm",
                                                 "company": "Other Co", "country": "Morocco"})
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/api/basins", headers=h, json={"name": "Pond A", "species": "common_carp", "capacity": 50,
                                                    "fish_count": 900})
    assert r.status_code == 201
    return h
