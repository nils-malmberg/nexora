from __future__ import annotations

import os

# Must be set before `app.config` is imported (by anything below):
# - the httpx-based TestClient talks to the app over plain http://testserver,
#   and a `Secure` cookie is silently dropped by any spec-compliant cookie
#   jar over plain HTTP, which would make every request after login look
#   unauthenticated (production keeps the secure default);
# - every market/FX provider is forced to the offline fixture/null adapters,
#   so the suite never makes a network call (specs/TESTING.md) and can never
#   burn a provider quota;
# - the prediction module is enabled and runs synchronously so its endpoints
#   can be exercised deterministically.
os.environ.setdefault("NEXORA_SESSION_COOKIE_SECURE", "false")
os.environ.setdefault("NEXORA_ENVIRONMENT", "test")
os.environ.setdefault("NEXORA_MARKET_EQUITY_PROVIDER", "fixture")
os.environ.setdefault("NEXORA_MARKET_CRYPTO_PROVIDER", "null")
os.environ.setdefault("NEXORA_MARKET_FX_PROVIDER", "fixture")
os.environ.setdefault("NEXORA_MARKET_FUNDAMENTALS_PROVIDER", "fixture")
os.environ.setdefault("NEXORA_PREDICTION_ENABLED", "true")
os.environ.setdefault("NEXORA_PORTFOLIOS_ENABLED", "true")  # the bookkeeping tests still run
os.environ.setdefault("NEXORA_SINGLE_USER", "false")  # tests exercise the account path explicitly
os.environ.setdefault("NEXORA_PREDICTION_MIN_OBSERVATIONS", "120")

from datetime import UTC, datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402,F401 - registers tables on Base.metadata
from app.api.deps import api_limiter  # noqa: E402
from app.api.routers import auth as auth_router  # noqa: E402
from app.db import Base, enable_sqlite_foreign_keys  # noqa: E402
from app.market import service as market_service  # noqa: E402
from app.market.http import reset_buckets  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def db_session():
    # StaticPool: a `sqlite:///:memory:` engine otherwise hands each thread
    # its own empty database, and the TestClient dispatches sync route
    # handlers via a thread pool.
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
def _reset_process_state():
    """Rate limiters, token buckets and in-process caches are module-level
    singletons (state persists across a real process's lifetime) - reset
    between tests so they can't leak from one test into another."""
    auth_router._login_limiter.clear()
    auth_router._register_limiter.clear()
    api_limiter.clear()
    reset_buckets()
    market_service.reset_caches()


@pytest.fixture()
def client(db_session):
    """A TestClient wired to the same in-memory SQLite session used by the
    test, via a get_db dependency override."""
    from app.api.deps import get_db
    from app.api.main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register(
    client, email: str = "alice@example.com", password: str = "correct horse battery staple"
) -> tuple[str, str]:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    body = response.json()
    return body["csrf_token"], body["user"]["id"]


@pytest.fixture()
def registered_user(client):
    """Registers a user and returns (client, csrf_token, user_id) — the
    client already carries the session cookie from the registration
    response, ready for authenticated requests. The first registered user
    is an admin (self-hosted convention)."""
    csrf_token, user_id = register(client)
    return client, csrf_token, user_id


def auth_headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token}


def utcnow() -> datetime:
    return datetime.now(UTC)


def days_ago(n: int) -> datetime:
    return utcnow() - timedelta(days=n)


# --- news & events helpers -----------------------------------------------------


@pytest.fixture()
def make_instrument(db_session):
    def _make(
        symbol: str = "DEMO",
        name: str = "Demo SA",
        exchange: str = "XPAR",
        currency: str = "EUR",
        asset_class: str = "action",
        user_id: str | None = None,
    ) -> models.Instrument:
        instrument = models.Instrument(
            symbol=symbol, name=name, exchange=exchange, currency=currency, asset_class=asset_class, user_id=user_id
        )
        db_session.add(instrument)
        db_session.commit()
        return instrument

    return _make


@pytest.fixture()
def make_provider(db_session):
    def _make(name: str, type: str, config: dict | None = None, enabled: bool = True) -> models.Provider:
        provider = models.Provider(name=name, type=type, config=config or {}, enabled=enabled)
        db_session.add(provider)
        db_session.commit()
        return provider

    return _make


def read_fixture_bytes(*parts: str) -> bytes:
    return (FIXTURES_DIR.joinpath(*parts)).read_bytes()


def read_fixture_text(*parts: str) -> str:
    return (FIXTURES_DIR.joinpath(*parts)).read_text(encoding="utf-8")
