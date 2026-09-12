from __future__ import annotations


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token}


def _make_portfolio(client, csrf_token: str) -> str:
    response = client.post("/api/v1/portfolios", json={"name": "P"}, headers=_headers(csrf_token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _make_instrument(client, csrf_token: str, symbol: str = "AAA") -> str:
    response = client.post(
        "/api/v1/instruments",
        json={"symbol": symbol, "name": "Acme", "asset_class": "action", "currency": "EUR"},
        headers=_headers(csrf_token),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _transaction(client, portfolio_id, csrf_token, **kwargs):
    payload = {"currency": "EUR", "fees": "0", **kwargs}
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions", json=payload, headers=_headers(csrf_token)
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_history_reflects_deposits_and_prices_over_time(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument_id = _make_instrument(client, csrf)

    _transaction(
        client, portfolio_id, csrf, type="depot", trade_date="2026-01-01T00:00:00Z", quantity="1", unit_price="5000"
    )
    _transaction(
        client,
        portfolio_id,
        csrf,
        type="achat",
        trade_date="2026-01-05T00:00:00Z",
        instrument_id=instrument_id,
        quantity="10",
        unit_price="100",
    )
    client.post(
        f"/api/v1/instruments/{instrument_id}/prices",
        json={"as_of": "2026-01-10T00:00:00Z", "price": "120", "currency": "EUR"},
        headers=_headers(csrf),
    )

    response = client.get(f"/api/v1/portfolios/{portfolio_id}/analytics/history")
    assert response.status_code == 200, response.text
    points = response.json()["points"]
    assert len(points) >= 3
    assert points[0]["total_value"] == "5000.000000"
    assert points[-1]["total_value"] == "5200.000000"  # 4000 cash + 10*120


def test_allocation_excludes_cash_and_sums_to_one(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument_id = _make_instrument(client, csrf)

    _transaction(
        client, portfolio_id, csrf, type="depot", trade_date="2026-01-01T00:00:00Z", quantity="1", unit_price="5000"
    )
    _transaction(
        client,
        portfolio_id,
        csrf,
        type="achat",
        trade_date="2026-01-02T00:00:00Z",
        instrument_id=instrument_id,
        quantity="10",
        unit_price="100",
    )
    client.post(
        f"/api/v1/instruments/{instrument_id}/prices",
        json={"as_of": "2026-01-03T00:00:00Z", "price": "100", "currency": "EUR"},
        headers=_headers(csrf),
    )

    response = client.get(f"/api/v1/portfolios/{portfolio_id}/analytics/allocation")
    body = response.json()
    assert body["total_value"] == "1000.000000"
    assert body["by_asset_class"] == [{"label": "action", "value": "1000.000000", "share": "1.0000"}]
    assert body["by_instrument"][0]["label"] == "AAA"


def test_allocation_lists_unconverted_currency_separately(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument = client.post(
        "/api/v1/instruments",
        json={"symbol": "USDX", "name": "US co", "asset_class": "action", "currency": "USD"},
        headers=_headers(csrf),
    ).json()
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument["id"],
            "type": "achat",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "10",
            "unit_price": "100",
            "currency": "USD",
        },
        headers=_headers(csrf),
    )
    client.post(
        f"/api/v1/instruments/{instrument['id']}/prices",
        json={"as_of": "2026-01-02T00:00:00Z", "price": "100", "currency": "USD"},
        headers=_headers(csrf),
    )

    response = client.get(f"/api/v1/portfolios/{portfolio_id}/analytics/allocation")
    body = response.json()
    assert body["total_value"] == "0"
    assert body["unconverted_currencies"] == ["USD"]


def test_risk_reports_insufficient_data_for_new_portfolio(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    _transaction(
        client, portfolio_id, csrf, type="depot", trade_date="2026-01-01T00:00:00Z", quantity="1", unit_price="1000"
    )

    response = client.get(f"/api/v1/portfolios/{portfolio_id}/analytics/risk")
    body = response.json()
    assert body["has_sufficient_data"] is False
    assert body["volatility_annualized"] is None


def test_performance_twr_mwr_simple_deposit_growth(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument_id = _make_instrument(client, csrf)

    _transaction(
        client, portfolio_id, csrf, type="depot", trade_date="2026-01-01T00:00:00Z", quantity="1", unit_price="1000"
    )
    _transaction(
        client,
        portfolio_id,
        csrf,
        type="achat",
        trade_date="2026-01-01T00:00:00Z",
        instrument_id=instrument_id,
        quantity="10",
        unit_price="100",
    )
    # A price at `start` itself is needed too - without it, the valuation at
    # `start` would have a missing price for the just-bought position (never
    # invented), and the whole period would be reported as insufficient data.
    client.post(
        f"/api/v1/instruments/{instrument_id}/prices",
        json={"as_of": "2026-01-01T00:00:00Z", "price": "100", "currency": "EUR"},
        headers=_headers(csrf),
    )
    client.post(
        f"/api/v1/instruments/{instrument_id}/prices",
        json={"as_of": "2027-01-01T00:00:00Z", "price": "110", "currency": "EUR"},
        headers=_headers(csrf),
    )

    response = client.get(
        f"/api/v1/portfolios/{portfolio_id}/analytics/performance",
        params={"start": "2026-01-01T00:00:00Z", "end": "2027-01-01T00:00:00Z"},
    )
    body = response.json()
    assert body["has_sufficient_data"] is True
    # Portfolio grew from 1000 to 1100 with no external flow in between -> 10%
    assert body["twr"] == "0.1000"
    assert body["external_flow_count"] == 0


def test_indicators_endpoint_returns_series(registered_user):
    client, csrf, _user_id = registered_user
    instrument_id = _make_instrument(client, csrf)
    for day, price in enumerate(["100", "101", "102", "103", "104"], start=1):
        client.post(
            f"/api/v1/instruments/{instrument_id}/prices",
            json={"as_of": f"2026-01-0{day}T00:00:00Z", "price": price, "currency": "EUR"},
            headers=_headers(csrf),
        )
    response = client.get(f"/api/v1/instruments/{instrument_id}/indicators", params={"sma": 3, "ema": 3, "rsi": 3})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["prices"]) == 5
    assert body["sma"][-1] is not None
    assert body["sma_window"] == 3


def test_analytics_tenant_isolation(registered_user):
    owner_client, owner_csrf, _owner_id = registered_user
    portfolio_id = _make_portfolio(owner_client, owner_csrf)

    owner_client.cookies.clear()
    register = owner_client.post(
        "/api/v1/auth/register",
        json={"email": "intruder-analytics@example.com", "password": "correct horse battery staple"},
    )
    assert register.status_code == 201

    response = owner_client.get(f"/api/v1/portfolios/{portfolio_id}/analytics/history")
    assert response.status_code == 404


def test_education_list_and_article(client):
    listing = client.get("/api/v1/education")
    assert listing.status_code == 200
    slugs = [a["slug"] for a in listing.json()]
    assert "valorisation" in slugs

    article = client.get("/api/v1/education/valorisation")
    assert article.status_code == 200
    body = article.json()
    assert body["title"]
    assert body["method"]
    assert body["limitations"]


def test_education_unknown_slug_is_404(client):
    response = client.get("/api/v1/education/does-not-exist")
    assert response.status_code == 404
