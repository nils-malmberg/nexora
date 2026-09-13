"""Market endpoints end to end, against the offline fixture provider (see
tests/conftest.py): search, catalog, quote caching, history, watchlist,
one-click purchase record, overview, rate limiting and breaker state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.config import settings
from app.market import registry
from app.market import service as market_service
from app.market.base import MarketUnavailable
from app.models import MarketProvider, PricePoint
from tests.conftest import auth_headers, register


def _headers(csrf):
    return auth_headers(csrf)


def _add_demo(client, csrf, symbol="DEMO"):
    resp = client.post(
        "/api/v1/market/catalog",
        json={
            "provider": "fixture",
            "provider_symbol": symbol,
            "symbol": symbol,
            "name": "Demo SA",
            "asset_class": "action",
        },
        headers=_headers(csrf),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_search_merges_local_catalog_and_provider(registered_user):
    client, csrf, _ = registered_user
    resp = client.get("/api/v1/market/search", params={"q": "demo"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["providers_queried"] == ["fixture"]
    symbols = {c["symbol"] for c in body["candidates"]}
    assert {"DEMO", "USDEMO"} <= symbols
    assert all(c["in_catalog"] is False for c in body["candidates"])

    # Adding one to the catalog makes it show as in_catalog with an id.
    added = _add_demo(client, csrf)
    assert added["created"] is True and added["instrument"]["is_shared"] is True
    assert added["instrument"]["currency"] == "EUR"  # filled from the first quote
    body = client.get("/api/v1/market/search", params={"q": "demo"}).json()
    demo = next(c for c in body["candidates"] if c["symbol"] == "DEMO")
    assert demo["in_catalog"] is True and demo["instrument_id"] == added["instrument"]["id"]

    # Idempotent: adding again returns the same row.
    again = client.post(
        "/api/v1/market/catalog",
        json={"provider": "fixture", "provider_symbol": "DEMO", "symbol": "DEMO", "name": "x", "asset_class": "action"},
        headers=_headers(csrf),
    )
    assert again.status_code == 201 and again.json()["created"] is False
    assert again.json()["instrument"]["id"] == added["instrument"]["id"]


def test_search_filters_by_asset_class_and_needs_auth(client, registered_user):
    http, csrf, _ = registered_user
    body = http.get("/api/v1/market/search", params={"q": "demo", "asset_class": "crypto"}).json()
    assert body["candidates"] == []  # crypto provider is "null" in tests
    assert body["providers_queried"] == []
    http.post("/api/v1/auth/logout", headers=_headers(csrf))
    assert http.get("/api/v1/market/search", params={"q": "demo"}).status_code == 401


def test_quote_is_cached_between_refreshes(registered_user, db_session):
    client, csrf, _ = registered_user
    instrument = _add_demo(client, csrf)["instrument"]
    first = client.get(f"/api/v1/market/instruments/{instrument['id']}/quote").json()
    assert first["status"] == "fresh"
    assert first["price"] == "42.500000" and first["currency"] == "EUR"
    assert first["source"] == "fixture" and first["is_delayed"] is True
    assert first["attribution"] and first["license_note"]
    n_points = len(db_session.scalars(select(PricePoint).where(PricePoint.instrument_id == instrument["id"])).all())
    # A second call within the freshness window serves the stored point: no new row.
    second = client.get(f"/api/v1/market/instruments/{instrument['id']}/quote").json()
    assert second["status"] == "fresh"
    assert (
        len(db_session.scalars(select(PricePoint).where(PricePoint.instrument_id == instrument["id"])).all())
        == n_points
    )


def test_quote_survives_provider_outage_as_stale(registered_user, db_session, monkeypatch):
    client, csrf, _ = registered_user
    instrument = _add_demo(client, csrf)["instrument"]
    # Force the cached point to look old, then break the provider.
    point = db_session.scalars(select(PricePoint).where(PricePoint.instrument_id == instrument["id"])).first()
    point.collected_at = datetime.now(UTC) - timedelta(hours=2)
    db_session.commit()
    provider = registry.build_provider("fixture")

    def _boom(symbol):
        raise MarketUnavailable("fixture: simulated outage")

    monkeypatch.setattr(provider, "quote", _boom)
    body = client.get(f"/api/v1/market/instruments/{instrument['id']}/quote").json()
    assert body["status"] == "stale" and body["reason"] == "unavailable"
    assert body["price"] == "42.500000"  # last known value still shown, flagged
    state = db_session.get(MarketProvider, "fixture")
    assert state.consecutive_failures == 1 and state.last_error


def test_provider_auto_disables_after_repeated_failures(registered_user, db_session, monkeypatch):
    client, csrf, _ = registered_user
    instrument = _add_demo(client, csrf)["instrument"]
    provider = registry.build_provider("fixture")
    monkeypatch.setattr(settings, "market_auto_disable_after_failures", 3)

    def _boom(symbol):
        raise MarketUnavailable("down")

    monkeypatch.setattr(provider, "quote", _boom)
    for _ in range(3):
        point = db_session.scalars(select(PricePoint).where(PricePoint.instrument_id == instrument["id"])).first()
        point.collected_at = datetime.now(UTC) - timedelta(hours=2)
        db_session.commit()
        state = db_session.get(MarketProvider, "fixture")
        state.circuit_state = "closed"  # re-open the breaker each time so the call actually happens
        db_session.commit()
        client.get(f"/api/v1/market/instruments/{instrument['id']}/quote")
    state = db_session.get(MarketProvider, "fixture")
    assert state.enabled is False and "auto-disabled" in state.disabled_reason
    body = client.get(f"/api/v1/market/instruments/{instrument['id']}/quote").json()
    assert body["reason"] == "circuit_open"
    # Admin re-enables it.
    resp = client.post("/api/v1/admin/market-providers/fixture/enabled", json={"enabled": True}, headers=_headers(csrf))
    assert resp.status_code == 200 and resp.json()["enabled"] is True and resp.json()["consecutive_failures"] == 0


def test_history_ranges_and_ohlc_flag(registered_user):
    client, csrf, _ = registered_user
    instrument = _add_demo(client, csrf)["instrument"]
    resp = client.get(f"/api/v1/market/instruments/{instrument['id']}/history", params={"range": "max"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_ohlc"] is True and body["source"] == "fixture"
    assert [b["close"] for b in body["bars"]] == ["40.000000", "40.000000", "41.200000", "42.500000"]
    assert body["bars"][0]["volume"] == "12000.0000"
    assert (
        client.get(f"/api/v1/market/instruments/{instrument['id']}/history", params={"range": "bogus"}).status_code
        == 400
    )


def test_close_only_history_is_a_line_not_fake_candles(registered_user):
    client, csrf, _ = registered_user
    resp = client.post(
        "/api/v1/market/catalog",
        json={
            "provider": "fixture",
            "provider_symbol": "bitcoin-demo",
            "symbol": "BTC",
            "name": "Bitcoin",
            "asset_class": "crypto",
        },
        headers=_headers(csrf),
    )
    instrument = resp.json()["instrument"]
    body = client.get(f"/api/v1/market/instruments/{instrument['id']}/history", params={"range": "max"}).json()
    assert body["has_ohlc"] is False
    assert all(b["open"] is None for b in body["bars"])
    assert [b["close"] for b in body["bars"]] == ["63000.000000", "64000.000000", "65000.000000"]


def test_watchlist_and_overview(registered_user):
    client, csrf, _ = registered_user
    instrument = _add_demo(client, csrf)["instrument"]
    assert client.get("/api/v1/market/watchlist").json() == []
    added = client.post("/api/v1/market/watchlist", json={"instrument_id": instrument["id"]}, headers=_headers(csrf))
    assert added.status_code == 201 and added.json()["quote"]["price"] == "42.500000"
    dup = client.post("/api/v1/market/watchlist", json={"instrument_id": instrument["id"]}, headers=_headers(csrf))
    assert dup.status_code == 409
    overview = client.get("/api/v1/market/overview").json()
    assert len(overview) == 1 and overview[0]["watched"] is True and overview[0]["held_quantity"] is None
    removed = client.delete(f"/api/v1/market/watchlist/{added.json()['id']}", headers=_headers(csrf))
    assert removed.status_code == 204
    assert client.get("/api/v1/market/overview").json() == []


def test_quick_buy_records_a_transaction_only(registered_user):
    client, csrf, _ = registered_user
    instrument = _add_demo(client, csrf)["instrument"]
    portfolio = client.post(
        "/api/v1/portfolios", json={"name": "PEA", "base_currency": "EUR"}, headers=_headers(csrf)
    ).json()
    resp = client.post(
        f"/api/v1/market/instruments/{instrument['id']}/quick-buy",
        json={"portfolio_id": portfolio["id"], "quantity": "3", "unit_price": "42.5", "currency": "EUR", "fees": "1"},
        headers=_headers(csrf),
    )
    assert resp.status_code == 201, resp.text
    tx = resp.json()
    assert tx["type"] == "achat" and tx["instrument_id"] == instrument["id"]
    valuation = client.get(f"/api/v1/portfolios/{portfolio['id']}/valuation").json()
    assert valuation["positions"][0]["quantity"] == "3.00000000"
    assert valuation["positions"][0]["price_source"] == "fixture"
    assert Decimal(valuation["positions"][0]["market_value"]) == Decimal("127.5")
    # Funded by a matching deposit by default: cash nets to zero, total = position.
    assert Decimal(valuation["cash"]) == Decimal("0")
    assert Decimal(valuation["total_value"]) == Decimal("127.5")
    txs = client.get(f"/api/v1/portfolios/{portfolio['id']}/transactions").json()["items"]
    assert [t["type"] for t in txs] == ["achat", "depot"]
    overview = client.get("/api/v1/market/overview").json()
    assert overview[0]["held_quantity"] == "3.00000000"

    # Without the deposit the purchase draws on tracked cash.
    resp = client.post(
        f"/api/v1/market/instruments/{instrument['id']}/quick-buy",
        json={
            "portfolio_id": portfolio["id"],
            "quantity": "1",
            "unit_price": "40",
            "currency": "EUR",
            "fund_with_deposit": False,
        },
        headers=_headers(csrf),
    )
    assert resp.status_code == 201
    assert Decimal(client.get(f"/api/v1/portfolios/{portfolio['id']}/valuation").json()["cash"]) == Decimal("-40")

    # Another user's portfolio is a 404, never usable.
    bob_csrf, _ = register(client, email="bob@example.com")
    resp = client.post(
        f"/api/v1/market/instruments/{instrument['id']}/quick-buy",
        json={"portfolio_id": portfolio["id"], "quantity": "1", "unit_price": "1", "currency": "EUR"},
        headers=_headers(bob_csrf),
    )
    assert resp.status_code == 404


def test_shared_catalog_instrument_is_read_only_for_users(registered_user):
    client, csrf, _ = registered_user
    instrument = _add_demo(client, csrf)["instrument"]
    resp = client.post(
        f"/api/v1/instruments/{instrument['id']}/prices",
        json={"as_of": "2026-01-02T00:00:00Z", "price": "1", "currency": "EUR"},
        headers=_headers(csrf),
    )
    assert resp.status_code == 403
    assert client.delete(f"/api/v1/instruments/{instrument['id']}", headers=_headers(csrf)).status_code == 403


def test_api_rate_limit_on_fan_out_endpoints(registered_user, monkeypatch):
    client, csrf, _ = registered_user
    from app.api import deps

    monkeypatch.setattr(deps.api_limiter, "_max_attempts", 3)
    for _ in range(3):
        assert client.get("/api/v1/market/search", params={"q": "demo"}).status_code == 200
    assert client.get("/api/v1/market/search", params={"q": "demo"}).status_code == 429


def test_catalog_add_with_unknown_provider_symbol_and_no_currency_is_503(registered_user):
    client, csrf, _ = registered_user
    resp = client.post(
        "/api/v1/market/catalog",
        json={
            "provider": "fixture",
            "provider_symbol": "NOQUOTE",
            "symbol": "NOQUOTE",
            "name": "No Quote",
            "asset_class": "action",
        },
        headers=_headers(csrf),
    )
    assert resp.status_code == 503  # no quote -> no currency -> refused rather than guessed
    resp = client.post(
        "/api/v1/market/catalog",
        json={
            "provider": "fixture",
            "provider_symbol": "NOQUOTE",
            "symbol": "NOQUOTE",
            "name": "No Quote",
            "asset_class": "action",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    assert resp.status_code == 201  # explicit currency supplied by the user
    quote = client.get(f"/api/v1/market/instruments/{resp.json()['instrument']['id']}/quote").json()
    assert quote["status"] == "unavailable" and quote["price"] is None and quote["freshness"] == "manquant"


def test_refresh_tracked_only_touches_held_or_watched(registered_user, db_session):
    client, csrf, _ = registered_user
    demo = _add_demo(client, csrf)["instrument"]
    client.post(
        "/api/v1/market/catalog",
        json={
            "provider": "fixture",
            "provider_symbol": "USDEMO",
            "symbol": "USDEMO",
            "name": "US Demo",
            "asset_class": "action",
        },
        headers=_headers(csrf),
    )
    client.post("/api/v1/market/watchlist", json={"instrument_id": demo["id"]}, headers=_headers(csrf))
    summary = market_service.refresh_tracked(db_session)
    assert summary["instruments"] == 1  # USDEMO is neither held nor watched: never refreshed
    assert summary["history_bars"] == 4


def test_watchlist_item_can_be_marked_as_held(registered_user):
    client, csrf, _ = registered_user
    instrument = _add_demo(client, csrf)["instrument"]
    item = client.post(
        "/api/v1/market/watchlist", json={"instrument_id": instrument["id"]}, headers=_headers(csrf)
    ).json()
    assert item["held"] is False and item["entry_price"] is None
    updated = client.patch(
        f"/api/v1/market/watchlist/{item['id']}",
        json={"held": True, "entry_price": "24.5", "quantity": "10", "note": "PEA"},
        headers=_headers(csrf),
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["held"] is True and body["entry_price"] == "24.500000" and body["quantity"] == "10.00000000"
    assert client.get("/api/v1/market/watchlist").json()[0]["note"] == "PEA"
    cleared = client.patch(f"/api/v1/market/watchlist/{item['id']}", json={"clear_entry": True}, headers=_headers(csrf))
    assert cleared.json()["entry_price"] is None and cleared.json()["held"] is True
    bad = client.patch(f"/api/v1/market/watchlist/{item['id']}", json={"entry_price": "-1"}, headers=_headers(csrf))
    assert bad.status_code == 422
    assert client.patch("/api/v1/market/watchlist/nope", json={"held": True}, headers=_headers(csrf)).status_code == 404
