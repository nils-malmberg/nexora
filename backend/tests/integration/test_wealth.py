"""Consolidated wealth, realized gains, income, informational alerts,
strategy study and rebased comparison — end to end, offline (fixture FX:
USD→EUR 0.92, EUR→USD 1.087; no market provider call is ever made)."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.domain.alerts import evaluate_alerts
from app.models import Notification, OhlcBar, PriceAlert, PricePoint
from tests.conftest import auth_headers, register
from tests.integration.test_quant_and_prediction import _seed_bars, _shared_instrument


def _h(csrf):
    return auth_headers(csrf)


def _portfolio(client, csrf, name="P", currency="EUR") -> str:
    resp = client.post("/api/v1/portfolios", json={"name": name, "base_currency": currency}, headers=_h(csrf))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _instrument(client, csrf, symbol="AAA", currency="EUR") -> str:
    resp = client.post(
        "/api/v1/instruments",
        json={"symbol": symbol, "name": f"{symbol} SA", "asset_class": "action", "currency": currency},
        headers=_h(csrf),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _tx(client, portfolio_id, csrf, **kwargs):
    payload = {"currency": "EUR", "fees": "0", **kwargs}
    resp = client.post(f"/api/v1/portfolios/{portfolio_id}/transactions", json=payload, headers=_h(csrf))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _price(client, csrf, instrument_id, price, as_of="2026-03-01T00:00:00Z", currency="EUR"):
    resp = client.post(
        f"/api/v1/instruments/{instrument_id}/prices",
        json={"as_of": as_of, "price": str(price), "currency": currency},
        headers=_h(csrf),
    )
    assert resp.status_code == 201, resp.text


# --- consolidated ---------------------------------------------------------------


def test_consolidated_converts_every_portfolio_into_the_reference_currency(registered_user):
    client, csrf, _ = registered_user
    eur = _portfolio(client, csrf, "Trade Republic", "EUR")
    usd = _portfolio(client, csrf, "Revolut", "USD")
    aaa = _instrument(client, csrf, "AAA", "EUR")
    bbb = _instrument(client, csrf, "BBB", "USD")
    _tx(client, eur, csrf, type="depot", trade_date="2026-01-01T00:00:00Z", quantity="1", unit_price="1000")
    _tx(
        client,
        eur,
        csrf,
        type="achat",
        trade_date="2026-01-02T00:00:00Z",
        instrument_id=aaa,
        quantity="5",
        unit_price="100",
    )
    _price(client, csrf, aaa, 120)
    _tx(
        client,
        usd,
        csrf,
        type="depot",
        trade_date="2026-01-01T00:00:00Z",
        quantity="1",
        unit_price="2000",
        currency="USD",
    )
    _tx(
        client,
        usd,
        csrf,
        type="achat",
        trade_date="2026-01-02T00:00:00Z",
        instrument_id=bbb,
        quantity="10",
        unit_price="50",
        currency="USD",
    )
    _price(client, csrf, bbb, 60, currency="USD")

    body = client.get("/api/v1/portfolios/consolidated").json()
    assert body["reference_currency"] == "EUR"
    # EUR portfolio: 500 cash + 600 positions = 1100 ; USD portfolio: 1500 cash + 600 = 2100 USD × 0.92 = 1932
    assert Decimal(body["total_value"]) == Decimal("3032.000000")
    assert Decimal(body["cash"]) == Decimal("500") + Decimal("1500") * Decimal("0.92")
    cards = {p["name"]: p for p in body["portfolios"]}
    assert cards["Revolut"]["fx_rate"] == "0.92000000" and cards["Revolut"]["fx_source"] == "fixture-fx"
    assert cards["Revolut"]["total_value_reference"] == "1932.000000"
    assert cards["Trade Republic"]["fx_source"] == "identity"
    by_portfolio = {s["label"]: s for s in body["by_portfolio"]}
    assert Decimal(by_portfolio["Revolut"]["share"]) + Decimal(by_portfolio["Trade Republic"]["share"]) == Decimal("1")
    classes = {s["label"] for s in body["by_asset_class"]}
    assert classes == {"tresorerie", "action"}
    assert body["unconverted_currencies"] == [] and body["has_missing_prices"] is False


def test_consolidated_lists_unconvertible_portfolio_and_is_per_user(registered_user, client):
    http, csrf, _ = registered_user
    chf = _portfolio(http, csrf, "Suisse", "CHF")
    _tx(
        http, chf, csrf, type="depot", trade_date="2026-01-01T00:00:00Z", quantity="1", unit_price="100", currency="CHF"
    )
    body = http.get("/api/v1/portfolios/consolidated").json()
    assert body["unconverted_currencies"] == ["CHF"]
    assert body["portfolios"][0]["total_value_reference"] is None
    assert body["total_value"] == "0.000000"

    http.post("/api/v1/auth/logout", headers=_h(csrf))
    csrf2, _ = register(http, "bob@example.com")
    other = http.get("/api/v1/portfolios/consolidated").json()
    assert other["portfolios"] == []


# --- realized gains and income ---------------------------------------------------


def test_realized_gains_fifo_per_year_and_instrument(registered_user):
    client, csrf, _ = registered_user
    p = _portfolio(client, csrf)
    aaa = _instrument(client, csrf, "AAA")
    _tx(client, p, csrf, type="depot", trade_date="2025-01-01T00:00:00Z", quantity="1", unit_price="10000")
    _tx(
        client,
        p,
        csrf,
        type="achat",
        trade_date="2025-01-02T00:00:00Z",
        instrument_id=aaa,
        quantity="10",
        unit_price="100",
        fees="10",
    )
    _tx(
        client,
        p,
        csrf,
        type="achat",
        trade_date="2025-02-02T00:00:00Z",
        instrument_id=aaa,
        quantity="10",
        unit_price="120",
    )
    _tx(
        client,
        p,
        csrf,
        type="vente",
        trade_date="2025-06-01T00:00:00Z",
        instrument_id=aaa,
        quantity="15",
        unit_price="130",
        fees="5",
    )
    _tx(
        client,
        p,
        csrf,
        type="vente",
        trade_date="2026-01-15T00:00:00Z",
        instrument_id=aaa,
        quantity="5",
        unit_price="90",
    )

    body = client.get(f"/api/v1/portfolios/{p}/analytics/realized").json()
    assert body["base_currency"] == "EUR" and body["mixed_currency_sales"] == 0
    first, second = body["sales"]
    # 15 × 130 − 5 = 1945 proceeds ; cost = 10 × 101 + 5 × 120 = 1610 → +335
    assert first["proceeds"] == "1945.000000" and first["cost_basis"] == "1610.000000"
    assert first["realized_pnl"] == "335.000000" and first["realized_pnl_base"] == "335.000000"
    assert first["holding_days"] == (datetime(2025, 6, 1) - datetime(2025, 1, 2)).days
    # 5 × 90 = 450 ; cost = 5 × 120 = 600 → −150
    assert second["realized_pnl"] == "-150.000000"
    years = {t["key"]: t for t in body["by_year"]}
    assert years["2025"]["gains_base"] == "335.000000" and years["2026"]["losses_base"] == "-150.000000"
    assert body["total_realized_pnl_base"] == "185.000000"
    assert body["by_instrument"][0]["label"] == "AAA" and body["by_instrument"][0]["sales"] == 2

    only_2026 = client.get(f"/api/v1/portfolios/{p}/analytics/realized", params={"year": 2026}).json()
    assert len(only_2026["sales"]) == 1 and only_2026["total_realized_pnl_base"] == "-150.000000"


def test_realized_flags_mixed_currency_and_converts_foreign_sales(registered_user):
    client, csrf, _ = registered_user
    p = _portfolio(client, csrf)  # EUR base
    usd = _instrument(client, csrf, "UUU", "USD")
    _tx(
        client,
        p,
        csrf,
        type="achat",
        trade_date="2025-01-02T00:00:00Z",
        instrument_id=usd,
        quantity="10",
        unit_price="100",
        currency="USD",
    )
    _tx(
        client,
        p,
        csrf,
        type="vente",
        trade_date="2025-03-02T00:00:00Z",
        instrument_id=usd,
        quantity="4",
        unit_price="150",
        currency="USD",
    )
    # Sold in EUR what was bought in USD: no single-currency P&L.
    _tx(
        client,
        p,
        csrf,
        type="vente",
        trade_date="2025-04-02T00:00:00Z",
        instrument_id=usd,
        quantity="2",
        unit_price="140",
        currency="EUR",
    )

    body = client.get(f"/api/v1/portfolios/{p}/analytics/realized").json()
    usd_sale, eur_sale = body["sales"]
    assert usd_sale["realized_pnl"] == "200.000000" and usd_sale["realized_pnl_base"] == "184.000000"
    assert usd_sale["fx_rate"] == "0.92000000"
    assert eur_sale["mixed_currency"] is True and eur_sale["realized_pnl"] is None
    assert body["mixed_currency_sales"] == 1
    assert body["total_realized_pnl_base"] == "184.000000"


def test_income_report_groups_dividends_interest_and_fees(registered_user):
    client, csrf, _ = registered_user
    p = _portfolio(client, csrf)
    aaa = _instrument(client, csrf, "AAA")
    _tx(
        client,
        p,
        csrf,
        type="achat",
        trade_date="2025-01-02T00:00:00Z",
        instrument_id=aaa,
        quantity="10",
        unit_price="100",
        fees="3",
    )
    _tx(
        client,
        p,
        csrf,
        type="dividende",
        trade_date="2025-04-10T00:00:00Z",
        instrument_id=aaa,
        quantity="1",
        unit_price="25",
        fees="1",
    )
    _tx(client, p, csrf, type="interet", trade_date="2025-12-31T00:00:00Z", quantity="1", unit_price="12.5")
    _tx(client, p, csrf, type="frais", trade_date="2026-01-05T00:00:00Z", quantity="1", unit_price="4")
    _tx(client, p, csrf, type="depot", trade_date="2025-01-01T00:00:00Z", quantity="1", unit_price="5000")  # not income

    body = client.get(f"/api/v1/portfolios/{p}/analytics/income").json()
    kinds = sorted((r["type"], r["amount"]) for r in body["rows"])
    assert kinds == [
        ("dividende", "24.000000"),
        ("frais", "-4.000000"),
        ("frais_transaction", "-3.000000"),
        ("interet", "12.500000"),
    ]
    assert body["total_income_base"] == "36.500000" and body["total_fees_base"] == "-7.000000"
    years = {t["key"]: t for t in body["by_year"]}
    assert years["2025"]["income_base"] == "36.500000" and years["2025"]["fees_base"] == "-3.000000"
    assert years["2025"]["net_base"] == "33.500000"
    assert [m["key"] for m in body["by_month"]] == ["2025-01", "2025-04", "2025-12", "2026-01"]
    assert body["by_instrument"][0]["label"] == "AAA" and body["by_instrument"][0]["count"] == 2

    only = client.get(f"/api/v1/portfolios/{p}/analytics/income", params={"year": 2026}).json()
    assert [r["type"] for r in only["rows"]] == ["frais"]


def test_reports_are_tenant_scoped(registered_user, client):
    http, csrf, _ = registered_user
    p = _portfolio(http, csrf)
    http.post("/api/v1/auth/logout", headers=_h(csrf))
    register(http, "bob@example.com")
    assert http.get(f"/api/v1/portfolios/{p}/analytics/realized").status_code == 404
    assert http.get(f"/api/v1/portfolios/{p}/analytics/income").status_code == 404


# --- alerts and notifications ----------------------------------------------------


def test_alert_lifecycle_triggers_once_and_notifies(registered_user, db_session):
    client, csrf, _ = registered_user
    aaa = _instrument(client, csrf, "AAA")
    _price(client, csrf, aaa, 100)

    resp = client.post(
        "/api/v1/alerts",
        json={"instrument_id": aaa, "kind": "price_above", "threshold": "110", "note": "seuil test"},
        headers=_h(csrf),
    )
    assert resp.status_code == 201, resp.text
    alert = resp.json()
    assert alert["active"] is True and alert["kind_label"] == "cours au-dessus de"
    assert alert["last_value"] == "100.000000" and alert["triggered_at"] is None

    # Nothing crossed yet.
    notes = client.get("/api/v1/notifications").json()
    assert notes["unread"] == 0 and notes["items"] == []

    _price(client, csrf, aaa, 115, as_of="2026-03-02T00:00:00Z")
    notes = client.get("/api/v1/notifications").json()
    assert notes["unread"] == 1
    item = notes["items"][0]
    assert item["alert_id"] == alert["id"] and item["kind"] == "price_above"
    assert "AAA" in item["title"] and "110" in item["title"] and "seuil test" in item["body"]

    # One-shot: the alert is now inactive and a further evaluation adds nothing.
    listed = client.get("/api/v1/alerts", params={"instrument_id": aaa}).json()
    assert listed[0]["active"] is False and listed[0]["triggered_at"] is not None
    assert evaluate_alerts(db_session) == 0
    assert db_session.scalar(select(Notification).where(Notification.alert_id == alert["id"]).limit(1)) is not None

    # Mark as read, then re-arm: it triggers again immediately since the price still crosses.
    read = client.post("/api/v1/notifications/read", json={"ids": [item["id"]]}, headers=_h(csrf)).json()
    assert read["unread"] == 0 and read["items"][0]["read_at"] is not None
    rearmed = client.post(f"/api/v1/alerts/{alert['id']}/rearm", headers=_h(csrf)).json()
    assert rearmed["active"] is False and rearmed["triggered_at"] is not None
    assert client.get("/api/v1/notifications").json()["unread"] == 1

    assert client.delete(f"/api/v1/alerts/{alert['id']}", headers=_h(csrf)).status_code == 204
    assert client.get("/api/v1/alerts").json() == []
    # Notification survives the alert's deletion (alert_id detached).
    remaining = client.get("/api/v1/notifications").json()["items"]
    assert len(remaining) == 2 and all(n["alert_id"] is None for n in remaining)
    assert client.delete(f"/api/v1/notifications/{remaining[0]['id']}", headers=_h(csrf)).status_code == 204


def test_move_pct_alert_uses_previous_daily_close(registered_user, db_session):
    client, csrf, _ = registered_user
    instrument = _shared_instrument(db_session, "MOV")
    _seed_bars(db_session, instrument.id, n=30, seed=3)
    last = db_session.scalars(
        select(OhlcBar).where(OhlcBar.instrument_id == instrument.id).order_by(OhlcBar.as_of.desc())
    ).first()
    # A quote 8 % above the last daily close, observed the next day (shared
    # instruments are read-only through the API: inserted directly).
    db_session.add(
        PricePoint(
            instrument_id=instrument.id,
            as_of=last.as_of + timedelta(days=1),
            price=Decimal(str(last.close)) * Decimal("1.08"),
            currency="EUR",
            source="fixture",
        )
    )
    db_session.commit()

    small = client.post(
        "/api/v1/alerts", json={"instrument_id": instrument.id, "kind": "move_pct", "threshold": "10"}, headers=_h(csrf)
    ).json()
    big = client.post(
        "/api/v1/alerts", json={"instrument_id": instrument.id, "kind": "move_pct", "threshold": "5"}, headers=_h(csrf)
    ).json()
    assert small["active"] is True and big["active"] is False
    notes = client.get("/api/v1/notifications", params={"unread_only": True}).json()
    assert notes["unread"] == 1 and "+8.00 %" in notes["items"][0]["title"]


def test_alert_validation_and_tenant_isolation(registered_user, client):
    http, csrf, _ = registered_user
    aaa = _instrument(http, csrf, "AAA")
    bad_kind = http.post(
        "/api/v1/alerts", json={"instrument_id": aaa, "kind": "moon", "threshold": "1"}, headers=_h(csrf)
    )
    assert bad_kind.status_code == 422
    bad_threshold = http.post(
        "/api/v1/alerts", json={"instrument_id": aaa, "kind": "price_above", "threshold": "0"}, headers=_h(csrf)
    )
    assert bad_threshold.status_code == 422
    no_csrf = http.post("/api/v1/alerts", json={"instrument_id": aaa, "kind": "price_above", "threshold": "1"})
    assert no_csrf.status_code == 403
    ok = http.post(
        "/api/v1/alerts", json={"instrument_id": aaa, "kind": "price_below", "threshold": "1"}, headers=_h(csrf)
    )
    assert ok.status_code == 201
    alert_id = ok.json()["id"]

    http.post("/api/v1/auth/logout", headers=_h(csrf))
    csrf2, _ = register(http, "bob@example.com")
    assert http.get("/api/v1/alerts").json() == []
    assert http.delete(f"/api/v1/alerts/{alert_id}", headers=_h(csrf2)).status_code == 404
    assert http.post(f"/api/v1/alerts/{alert_id}/rearm", headers=_h(csrf2)).status_code == 404
    # Bob cannot alert on Alice's private instrument (404, not 403: no existence leak).
    hidden = http.post(
        "/api/v1/alerts", json={"instrument_id": aaa, "kind": "price_above", "threshold": "1"}, headers=_h(csrf2)
    )
    assert hidden.status_code == 404
    assert http.get("/api/v1/notifications").json()["unread"] == 0


def test_alerts_appear_in_data_export(registered_user):
    client, csrf, _ = registered_user
    aaa = _instrument(client, csrf, "AAA")
    client.post(
        "/api/v1/alerts", json={"instrument_id": aaa, "kind": "price_above", "threshold": "5"}, headers=_h(csrf)
    )
    export = client.get("/api/v1/me/export").json()
    assert len(export["alerts"]) == 1 and export["alerts"][0]["threshold"] == "5.000000"
    assert export["notifications"] == []


def test_worker_evaluation_covers_every_user(registered_user, db_session):
    client, csrf, user_id = registered_user
    instrument = _shared_instrument(db_session, "ALL")
    _seed_bars(db_session, instrument.id, n=20, seed=5)
    db_session.add(
        PriceAlert(user_id=user_id, instrument_id=instrument.id, kind="price_below", threshold=Decimal("1e6"))
    )
    db_session.commit()
    assert evaluate_alerts(db_session) == 1
    assert db_session.scalar(select(Notification).where(Notification.user_id == user_id).limit(1)) is not None


# --- strategy study and comparison ------------------------------------------------


def test_strategy_study_endpoint(registered_user, db_session):
    client, csrf, _ = registered_user
    instrument = _shared_instrument(db_session, "STRAT")
    _seed_bars(db_session, instrument.id, n=400, seed=7)

    resp = client.get(
        f"/api/v1/instruments/{instrument.id}/analytics/strategy-study",
        params={"rule": "sma_cross", "fast": 10, "slow": 30, "days": 400, "fee_bps": 10},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_sufficient_data"] and body["symbol"] == "STRAT"
    assert len(body["dates"]) == len(body["strategy_equity"]) == len(body["benchmark_equity"]) == len(body["invested"])
    assert body["strategy_equity"][0] == 1.0 and body["benchmark_equity"][0] == 1.0
    assert (
        body["strategy_stats"]["has_sufficient_data"]
        and body["benchmark_stats"]["observations"] == len(body["dates"]) - 1
    )
    assert body["n_trades"] == len(body["trades"]) and set(body["invested"]) <= {0, 1}
    assert "pédagogique" in body["disclaimer"]

    assert (
        client.get(f"/api/v1/instruments/{instrument.id}/analytics/strategy-study", params={"rule": "x"}).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/v1/instruments/{instrument.id}/analytics/strategy-study",
            params={"rule": "sma_cross", "fast": 50, "slow": 20},
        ).status_code
        == 422
    )
    rsi = client.get(
        f"/api/v1/instruments/{instrument.id}/analytics/strategy-study", params={"rule": "rsi_reversion", "days": 400}
    ).json()
    assert rsi["rule"] == "rsi_reversion" and rsi["params"]["rsi_low"] == 30.0


def test_compare_rebases_on_common_dates(registered_user, db_session):
    client, csrf, _ = registered_user
    a = _shared_instrument(db_session, "CMPA")
    b = _shared_instrument(db_session, "CMPB", currency="USD")
    _seed_bars(db_session, a.id, n=120, seed=1)
    _seed_bars(db_session, b.id, n=90, seed=2, currency="USD")

    resp = client.get("/api/v1/market/compare", params={"instrument_ids": f"{a.id},{b.id},{a.id}", "days": 200})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["observations"] == 90 and body["base"] == 100.0
    assert [s["instrument"]["symbol"] for s in body["series"]] == ["CMPA", "CMPB"]  # duplicates dropped
    for s in body["series"]:
        assert s["values"][0] == 100.0 and len(s["values"]) == 90
        assert s["total_return"] is not None

    assert client.get("/api/v1/market/compare", params={"instrument_ids": ""}).status_code == 422
    too_many = ",".join(f"x{i}" for i in range(7))
    assert client.get("/api/v1/market/compare", params={"instrument_ids": too_many}).status_code == 422
    assert client.get("/api/v1/market/compare", params={"instrument_ids": "missing"}).status_code == 404
