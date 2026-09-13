"""Product switches: single-user local session and the portfolio feature
switch (both are off/on differently in tests than in production defaults)."""

from __future__ import annotations

from app.config import settings
from tests.conftest import auth_headers


def test_local_session_only_in_single_user_mode(client, monkeypatch):
    assert client.post("/api/v1/auth/local").status_code == 404
    monkeypatch.setattr(settings, "single_user", True)
    first = client.post("/api/v1/auth/local")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["user"]["email"] == settings.single_user_email and body["user"]["is_admin"] is True
    # Session works and CSRF is enforced as for any account.
    assert client.get("/api/v1/me/export").status_code == 200
    assert client.post("/api/v1/market/watchlist", json={"instrument_id": "x"}).status_code == 403
    # Same account again, never a duplicate.
    again = client.post("/api/v1/auth/local").json()
    assert again["user"]["id"] == body["user"]["id"]
    # The built-in account cannot be logged into with a password.
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": settings.single_user_email, "password": "not-the-random-one"}
        ).status_code
        == 401
    )
    client.post("/api/v1/auth/logout", headers=auth_headers(again["csrf_token"]))


def test_public_config_and_portfolio_switch(registered_user, monkeypatch):
    client, csrf, _ = registered_user
    cfg = client.get("/api/v1/config").json()
    assert cfg["portfolios_enabled"] is True and cfg["single_user"] is False
    assert client.get("/api/v1/portfolios").status_code == 200
    monkeypatch.setattr(settings, "portfolios_enabled", False)
    assert client.get("/api/v1/config").json()["portfolios_enabled"] is False
    assert client.get("/api/v1/portfolios").status_code == 404
    assert client.get("/api/v1/portfolios/consolidated").status_code == 404
    assert client.post("/api/v1/portfolios", json={"name": "P"}, headers=auth_headers(csrf)).status_code == 404
    assert client.get("/api/v1/market/overview").status_code == 200  # the market side is untouched
