from __future__ import annotations


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token}


def test_create_and_search_instrument(registered_user):
    client, csrf, _user_id = registered_user
    created = client.post(
        "/api/v1/instruments",
        json={"symbol": "MSFT", "name": "Microsoft Corp", "asset_class": "action", "currency": "USD"},
        headers=_headers(csrf),
    )
    assert created.status_code == 201, created.text

    found = client.get("/api/v1/instruments/search", params={"q": "micro"})
    assert found.status_code == 200
    assert len(found.json()) == 1

    not_found = client.get("/api/v1/instruments/search", params={"q": "nonexistent"})
    assert not_found.json() == []


def test_duplicate_symbol_for_same_user_rejected(registered_user):
    client, csrf, _user_id = registered_user
    payload = {"symbol": "DUP", "name": "First", "asset_class": "action", "currency": "EUR"}
    first = client.post("/api/v1/instruments", json=payload, headers=_headers(csrf))
    assert first.status_code == 201
    second = client.post("/api/v1/instruments", json=payload, headers=_headers(csrf))
    assert second.status_code == 409


def test_invalid_asset_class_rejected(registered_user):
    client, csrf, _user_id = registered_user
    response = client.post(
        "/api/v1/instruments",
        json={"symbol": "X", "name": "X", "asset_class": "not_a_real_class", "currency": "EUR"},
        headers=_headers(csrf),
    )
    assert response.status_code == 422


def test_private_valuation_requires_actif_prive_asset_class(registered_user):
    client, csrf, _user_id = registered_user
    instrument = client.post(
        "/api/v1/instruments",
        json={"symbol": "PUB", "name": "Public co", "asset_class": "action", "currency": "EUR"},
        headers=_headers(csrf),
    ).json()

    response = client.post(
        f"/api/v1/instruments/{instrument['id']}/private-valuations",
        json={"valuation_date": "2026-01-01T00:00:00Z", "valuation_amount": "1000", "currency": "EUR", "method": "DCF"},
        headers=_headers(csrf),
    )
    assert response.status_code == 422


def test_private_valuation_feeds_position_price(registered_user):
    client, csrf, _user_id = registered_user
    portfolio = client.post("/api/v1/portfolios", json={"name": "P"}, headers=_headers(csrf)).json()
    instrument = client.post(
        "/api/v1/instruments",
        json={"symbol": "PRIV", "name": "Startup SAS", "asset_class": "actif_prive", "currency": "EUR"},
        headers=_headers(csrf),
    ).json()

    client.post(
        f"/api/v1/portfolios/{portfolio['id']}/transactions",
        json={
            "instrument_id": instrument["id"],
            "type": "achat",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "1",
            "unit_price": "10000",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    valuation_response = client.post(
        f"/api/v1/instruments/{instrument['id']}/private-valuations",
        json={
            "valuation_date": "2026-06-01T00:00:00Z",
            "valuation_amount": "15000",
            "currency": "EUR",
            "method": "Dernière levée de fonds",
            "confidence": "0.4",
        },
        headers=_headers(csrf),
    )
    assert valuation_response.status_code == 201

    positions = client.get(f"/api/v1/portfolios/{portfolio['id']}/positions").json()
    assert positions[0]["market_value"] == "15000.000000"
    assert positions[0]["freshness"] == "estime"


def test_instrument_not_owned_by_caller_is_404(registered_user):
    owner_client, owner_csrf, _owner_id = registered_user
    instrument = owner_client.post(
        "/api/v1/instruments",
        json={"symbol": "OWN", "name": "Owned", "asset_class": "action", "currency": "EUR"},
        headers=_headers(owner_csrf),
    ).json()

    owner_client.cookies.clear()
    owner_client.post(
        "/api/v1/auth/register", json={"email": "other@example.com", "password": "correct horse battery staple"}
    )

    response = owner_client.get(f"/api/v1/instruments/{instrument['id']}")
    assert response.status_code == 404
