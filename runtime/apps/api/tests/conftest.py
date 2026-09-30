"""Shared test fixtures.

Tests run against a REAL PostgreSQL database (`kynd_os_test`), not SQLite and
not a mock. The tenancy and constraint behaviour being tested — unique indexes,
cascade deletes, enum types, transactional integrity — is Postgres behaviour,
and a SQLite stand-in would prove something different from what ships.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The enforcement core lives at the repo root's src/. Adding it here means the
# API test suite always runs against the REAL kynd_runtime rather than needing
# an env var set by hand — and against the working tree, so a runtime change
# that broke the SaaS adapter would be caught immediately.
_RUNTIME_SRC = Path(__file__).resolve().parents[3] / "src"
if str(_RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_SRC))

os.environ.setdefault("KYND_ENVIRONMENT", "test")
os.environ.setdefault(
    "KYND_DATABASE_URL", "postgresql+psycopg://localhost/kynd_os_test"
)
os.environ.setdefault("KYND_COOKIE_SECURE", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from kynd_api.config import get_settings
from kynd_api.models import Base

TEST_DATABASE_URL = os.environ["KYND_DATABASE_URL"]


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    """Build the schema once for the session from the models' metadata."""
    engine = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate between tests so each starts from a known-empty database.

    TRUNCATE ... CASCADE rather than dropping and recreating: two orders of
    magnitude faster, and it also resets the state a foreign key would hold.
    """
    engine = create_engine(TEST_DATABASE_URL, future=True)
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE sessions, memberships, workspaces, users RESTART IDENTITY CASCADE")
        )
    engine.dispose()
    yield


@pytest.fixture
def db():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Rate limiters are process-global; a prior test must not throttle the next."""
    from kynd_api.routers import auth as auth_router

    auth_router._login_limiter.reset_all()
    auth_router._signup_limiter.reset_all()
    yield


@pytest.fixture
def client():
    """A TestClient WITHOUT cookie persistence between requests."""
    from kynd_api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def signup_user(
    client: TestClient,
    email: str = "owner@example.com",
    password: str = "correct-horse-battery-staple",
    workspace_name: str = "Acme Inc",
    name: str | None = "Test Owner",
) -> dict:
    """Sign up and return the parsed response. The client keeps the cookie."""
    response = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": password,
            "workspace_name": workspace_name,
            "name": name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def owner(client):
    """A signed-up, logged-in OWNER of a fresh workspace."""
    return signup_user(client)
