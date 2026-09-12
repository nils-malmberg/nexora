from __future__ import annotations

import os

# Must be set before `app.config` is imported (by anything below) - the
# httpx-based TestClient talks to the app over plain http://testserver, and a
# `Secure` cookie is silently dropped by any spec-compliant cookie jar over
# plain HTTP, which would make every request after login/register look
# unauthenticated. Production always overrides this back to true (or simply
# leaves the default), never the other way around.
os.environ.setdefault("NEXORA_PORTFOLIO_SESSION_COOKIE_SECURE", "false")

from datetime import UTC, datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402,F401 - registers tables on Base.metadata
from app.api.routers import auth as auth_router  # noqa: E402
from app.db import Base, enable_sqlite_foreign_keys  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def db_session():
    # StaticPool: a `sqlite:///:memory:` engine otherwise hands each thread
    # its own empty database, and the TestClient dispatches sync route
    # handlers via a thread pool - without this, requests in the `client`
    # fixture below would silently see an empty DB (verified in the News &
    # Events module's own test suite, which uses the same fix).
    engine = enable_sqlite_foreign_keys(
        create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def _reset_auth_rate_limiters():
    """The login/register limiters are module-level singletons (so state
    persists across a real process's lifetime) - reset between tests so one
    test's failed-login attempts don't 429 an unrelated later test, since the
    TestClient always reports the same fake client IP."""
    auth_router._login_limiter.clear()
    auth_router._register_limiter.clear()


@pytest.fixture()
def client(db_session):
    """A TestClient wired to the same in-memory SQLite session used by the
    test, via a get_db dependency override — so assertions can inspect rows
    the API just wrote without a second, separate database."""
    from app.api.deps import get_db
    from app.api.main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def registered_user(client):
    """Registers a user and returns (client, csrf_token, user_id) — the
    client already carries the session cookie from the registration
    response, ready for authenticated requests."""
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return client, body["csrf_token"], body["user"]["id"]


def auth_headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token}


def utcnow() -> datetime:
    return datetime.now(UTC)


def days_ago(n: int) -> datetime:
    return utcnow() - timedelta(days=n)
