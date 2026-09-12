from __future__ import annotations


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token}


def _make_portfolio(client, csrf_token: str, base_currency: str = "EUR") -> str:
    response = client.post(
        "/api/v1/portfolios", json={"name": "P", "base_currency": base_currency}, headers=_headers(csrf_token)
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _make_instrument(client, csrf_token: str, symbol: str = "AAA", currency: str = "EUR") -> str:
    response = client.post(
        "/api/v1/instruments",
        json={"symbol": symbol, "name": "Acme", "asset_class": "action", "currency": currency},
        headers=_headers(csrf_token),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_buy_creates_position(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument_id = _make_instrument(client, csrf)

    buy = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument_id,
            "type": "achat",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "10",
            "unit_price": "100",
            "currency": "EUR",
            "fees": "5",
        },
        headers=_headers(csrf),
    )
    assert buy.status_code == 201, buy.text

    positions = client.get(f"/api/v1/portfolios/{portfolio_id}/positions").json()
    assert len(positions) == 1
    assert positions[0]["quantity"] == "10.00000000"
    assert positions[0]["average_unit_cost"] == "100.500000"
    assert positions[0]["freshness"] == "manquant"
    assert positions[0]["market_value"] is None


def test_valuation_reflects_manual_price_and_cash(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument_id = _make_instrument(client, csrf)

    client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "type": "depot",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "1",
            "unit_price": "5000",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument_id,
            "type": "achat",
            "trade_date": "2026-01-02T00:00:00Z",
            "quantity": "10",
            "unit_price": "100",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    client.post(
        f"/api/v1/instruments/{instrument_id}/prices",
        json={"as_of": "2026-01-03T00:00:00Z", "price": "120", "currency": "EUR"},
        headers=_headers(csrf),
    )

    valuation = client.get(f"/api/v1/portfolios/{portfolio_id}/valuation").json()
    assert valuation["cash"] == "4000.000000"  # 5000 deposit - 1000 spent on the buy
    assert valuation["positions_value"] == "1200.000000"  # 10 * 120
    assert valuation["total_value"] == "5200.000000"
    assert valuation["has_missing_prices"] is False
    assert valuation["unconverted_currencies"] == []


def test_position_in_foreign_currency_is_excluded_from_total(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf, base_currency="EUR")
    instrument_id = _make_instrument(client, csrf, symbol="USD-STOCK", currency="USD")

    client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument_id,
            "type": "achat",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "10",
            "unit_price": "100",
            "currency": "USD",
        },
        headers=_headers(csrf),
    )
    client.post(
        f"/api/v1/instruments/{instrument_id}/prices",
        json={"as_of": "2026-01-02T00:00:00Z", "price": "110", "currency": "USD"},
        headers=_headers(csrf),
    )

    valuation = client.get(f"/api/v1/portfolios/{portfolio_id}/valuation").json()
    assert valuation["positions_value"] == "0.000000"
    assert valuation["unconverted_currencies"] == ["USD"]


def test_oversell_rejected_with_422(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument_id = _make_instrument(client, csrf)

    client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument_id,
            "type": "achat",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "5",
            "unit_price": "100",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    oversell = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument_id,
            "type": "vente",
            "trade_date": "2026-01-02T00:00:00Z",
            "quantity": "10",
            "unit_price": "100",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    assert oversell.status_code == 422

    # The rejected transaction must not have been persisted at all.
    transactions = client.get(f"/api/v1/portfolios/{portfolio_id}/transactions").json()["items"]
    assert len(transactions) == 1


def test_cash_only_transaction_requires_quantity_one(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)

    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "type": "depot",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "2",
            "unit_price": "500",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    assert response.status_code == 422


def test_transfert_type_not_yet_supported_via_api(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)

    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "type": "transfert",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "1",
            "unit_price": "1",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    assert response.status_code == 422


def test_valorisation_privee_transaction_creates_valuation_and_price(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument = client.post(
        "/api/v1/instruments",
        json={"symbol": "PRIV2", "name": "Startup SAS", "asset_class": "actif_prive", "currency": "EUR"},
        headers=_headers(csrf),
    ).json()

    # Record the initial stake so the instrument shows up as a position at all.
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
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

    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument["id"],
            "type": "valorisation_privee",
            "trade_date": "2026-06-01T00:00:00Z",
            "quantity": "1",
            "unit_price": "15000",
            "currency": "EUR",
            "method": "Dernière levée de fonds",
        },
        headers=_headers(csrf),
    )
    assert response.status_code == 201, response.text

    valuations = client.get(f"/api/v1/instruments/{instrument['id']}/private-valuations").json()
    assert len(valuations) == 1
    assert valuations[0]["valuation_amount"] == "15000.000000"

    positions = client.get(f"/api/v1/portfolios/{portfolio_id}/positions").json()
    assert positions[0]["market_value"] == "15000.000000"
    assert positions[0]["freshness"] == "estime"


def test_valorisation_privee_requires_method(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument = client.post(
        "/api/v1/instruments",
        json={"symbol": "PRIV3", "name": "Startup SAS", "asset_class": "actif_prive", "currency": "EUR"},
        headers=_headers(csrf),
    ).json()

    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument["id"],
            "type": "valorisation_privee",
            "trade_date": "2026-06-01T00:00:00Z",
            "quantity": "1",
            "unit_price": "15000",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    assert response.status_code == 422


def test_valorisation_privee_rejected_for_non_private_asset_class(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument_id = _make_instrument(client, csrf, symbol="PUB2")

    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument_id,
            "type": "valorisation_privee",
            "trade_date": "2026-06-01T00:00:00Z",
            "quantity": "1",
            "unit_price": "15000",
            "currency": "EUR",
            "method": "Estimation",
        },
        headers=_headers(csrf),
    )
    assert response.status_code == 422


def test_reverse_transaction_excludes_it_from_positions(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument_id = _make_instrument(client, csrf)

    buy = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument_id,
            "type": "achat",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "10",
            "unit_price": "100",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    tx_id = buy.json()["id"]

    reverse = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions/{tx_id}/reverse",
        json={"reason": "saisie en double"},
        headers=_headers(csrf),
    )
    assert reverse.status_code == 200
    assert reverse.json()["reversed_at"] is not None

    positions = client.get(f"/api/v1/portfolios/{portfolio_id}/positions").json()
    assert positions == []


def test_reverse_twice_conflicts(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument_id = _make_instrument(client, csrf)

    buy = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument_id,
            "type": "achat",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "10",
            "unit_price": "100",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    tx_id = buy.json()["id"]
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions/{tx_id}/reverse",
        json={"reason": "first"},
        headers=_headers(csrf),
    )
    second = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions/{tx_id}/reverse",
        json={"reason": "second"},
        headers=_headers(csrf),
    )
    assert second.status_code == 409


def test_reversing_a_buy_that_a_later_sell_depends_on_is_rejected(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument_id = _make_instrument(client, csrf)

    buy = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument_id,
            "type": "achat",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "5",
            "unit_price": "100",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    tx_id = buy.json()["id"]
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument_id,
            "type": "vente",
            "trade_date": "2026-01-02T00:00:00Z",
            "quantity": "5",
            "unit_price": "110",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )

    reverse = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions/{tx_id}/reverse",
        json={"reason": "oops"},
        headers=_headers(csrf),
    )
    assert reverse.status_code == 422


def test_split_doubles_quantity_and_halves_average_cost(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument_id = _make_instrument(client, csrf)

    client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument_id,
            "type": "achat",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "10",
            "unit_price": "100",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    split = client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument_id,
            "type": "split",
            "trade_date": "2026-01-02T00:00:00Z",
            "quantity": "2",
            "unit_price": "1",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    assert split.status_code == 201

    positions = client.get(f"/api/v1/portfolios/{portfolio_id}/positions").json()
    assert positions[0]["quantity"] == "20.00000000"
    assert positions[0]["average_unit_cost"] == "50.000000"


def test_duplicate_external_id_rejected(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)

    payload = {
        "type": "depot",
        "trade_date": "2026-01-01T00:00:00Z",
        "quantity": "1",
        "unit_price": "100",
        "currency": "EUR",
        "external_id": "csv-row-1",
    }
    first = client.post(f"/api/v1/portfolios/{portfolio_id}/transactions", json=payload, headers=_headers(csrf))
    assert first.status_code == 201
    second = client.post(f"/api/v1/portfolios/{portfolio_id}/transactions", json=payload, headers=_headers(csrf))
    assert second.status_code == 409
