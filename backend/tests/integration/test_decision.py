"""Decision-aid endpoints end to end: instrument readings with cached
fundamentals (fixture provider), market overview from stored data only,
portfolio check-up with targets, tenant isolation, provider budget."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import settings
from app.market import registry
from app.market import service as market_service
from app.market.base import MarketMisconfigured, MarketNotSupported
from app.models import InstrumentFundamentals, OhlcBar
from tests.conftest import auth_headers, register
from tests.integration.test_quant_and_prediction import _seed_bars, _shared_instrument


def _h(csrf):
    return auth_headers(csrf)


def _demo_instrument(client, csrf, symbol="DEMO"):
    resp = client.post(
        "/api/v1/market/catalog",
        json={
            "provider": "fixture",
            "provider_symbol": symbol,
            "symbol": symbol,
            "name": "Demo",
            "asset_class": "action",
        },
        headers=_h(csrf),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["instrument"]


def test_instrument_decision_aid_combines_technical_and_fundamental_readings(registered_user, db_session):
    client, csrf, _ = registered_user
    instrument = _demo_instrument(client, csrf)
    _seed_bars(db_session, instrument["id"], n=400, seed=11)

    resp = client.get(f"/api/v1/instruments/{instrument['id']}/decision-aid")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    keys = {s["key"] for s in body["signals"]}
    assert {"tendance_sma", "momentum_12_1", "rsi", "macd", "per", "consensus_analystes", "volatilite"} <= keys
    assert body["fundamentals"]["status"] == "fresh" and body["fundamentals"]["source"] == "fixture"
    per = next(s for s in body["signals"] if s["key"] == "per")
    assert per["reading"] == "favorable" and per["value"] == "12.4" and per["help_slug"] == "analyse-fondamentale"
    assert body["tally"]["available"] >= 15 and body["overall"]
    assert {h["horizon"] for h in body["horizons"]} == {"court_terme", "long_terme", "transversal"}
    assert "conseil" in body["disclaimer"] and body["prediction_available"] is False
    assert body["news_last_7_days"] == 0

    # Cached for 24 h: the row exists and a second call does not hit the provider.
    row = db_session.get(InstrumentFundamentals, instrument["id"])
    assert row is not None and row.data["pe"].startswith("12.4")
    calls = {"n": 0}
    original = registry.build_provider("fixture").fundamentals

    def counting(symbol):
        calls["n"] += 1
        return original(symbol)

    registry.build_provider("fixture").fundamentals = counting  # type: ignore[method-assign]
    try:
        again = client.get(f"/api/v1/instruments/{instrument['id']}/decision-aid").json()
        assert again["fundamentals"]["status"] == "fresh" and calls["n"] == 0
        forced = client.get(
            f"/api/v1/instruments/{instrument['id']}/decision-aid", params={"refresh_fundamentals": True}
        ).json()
        assert forced["fundamentals"]["status"] == "fresh" and calls["n"] == 1
    finally:
        del registry.build_provider("fixture").fundamentals


def test_decision_aid_without_fundamentals_for_private_instrument(registered_user, db_session):
    client, csrf, _ = registered_user
    resp = client.post(
        "/api/v1/instruments",
        json={"symbol": "PRIV", "name": "Private", "asset_class": "action", "currency": "EUR"},
        headers=_h(csrf),
    )
    instrument_id = resp.json()["id"]
    _seed_bars(db_session, instrument_id, n=60, seed=3)
    body = client.get(f"/api/v1/instruments/{instrument_id}/decision-aid").json()
    assert body["fundamentals"]["status"] == "not_supported"
    keys = {s["key"] for s in body["signals"]}
    assert "per" not in keys and "rsi" in keys
    unavailable = [s for s in body["signals"] if s["reading"] == "indisponible"]
    assert any(s["key"] == "momentum_12_1" for s in unavailable)  # 60 bars: not enough for 12-1 momentum


def test_fundamentals_service_statuses(registered_user, db_session, monkeypatch):
    client, csrf, _ = registered_user
    etf = db_session.get(type(_shared_instrument(db_session, "ETFX")), _shared_instrument(db_session, "ETFY").id)
    etf.asset_class = "etf"
    db_session.commit()
    assert market_service.get_fundamentals(db_session, etf).status == "not_supported"

    equity = _shared_instrument(db_session, "EQX")
    provider = registry.build_provider("fixture")

    def unsupported(symbol):
        raise MarketNotSupported("fixture: nope")

    monkeypatch.setattr(provider, "fundamentals", unsupported)
    view = market_service.get_fundamentals(db_session, equity)
    assert view.status == "not_supported" and view.row is None
    # The miss is remembered: a second call is answered without the provider.
    monkeypatch.setattr(provider, "fundamentals", lambda s: (_ for _ in ()).throw(AssertionError("called")))
    assert market_service.get_fundamentals(db_session, equity).status == "unavailable"
    market_service.reset_caches()

    def misconfigured(symbol):
        raise MarketMisconfigured("no key")

    monkeypatch.setattr(provider, "fundamentals", misconfigured)
    assert market_service.get_fundamentals(db_session, equity).status == "not_configured"

    monkeypatch.setattr(settings, "market_fundamentals_provider", "null")
    assert market_service.get_fundamentals(db_session, equity).status == "not_configured"


def test_market_decision_overview_uses_stored_data_only(registered_user, db_session, monkeypatch):
    client, csrf, _ = registered_user
    held = _demo_instrument(client, csrf)
    _seed_bars(db_session, held["id"], n=300, seed=5)
    watched = _shared_instrument(db_session, "WATCH")
    _seed_bars(db_session, watched.id, n=40, seed=6)
    portfolio = client.post("/api/v1/portfolios", json={"name": "P"}, headers=_h(csrf)).json()
    client.post(
        f"/api/v1/portfolios/{portfolio['id']}/transactions",
        json={
            "instrument_id": held["id"],
            "type": "achat",
            "trade_date": (datetime.now(UTC) - timedelta(days=10)).isoformat(),
            "quantity": "3",
            "unit_price": "100",
            "currency": "EUR",
        },
        headers=_h(csrf),
    )
    added = client.post("/api/v1/market/watchlist", json={"instrument_id": watched.id}, headers=_h(csrf))
    assert added.status_code == 201, added.text

    provider = registry.build_provider("fixture")
    monkeypatch.setattr(provider, "fundamentals", lambda s: (_ for _ in ()).throw(AssertionError("provider called")))
    monkeypatch.setattr(provider, "history", lambda *a, **k: (_ for _ in ()).throw(AssertionError("provider called")))

    body = client.get("/api/v1/market/decision-overview").json()
    assert body["fundamentals_configured"] is True
    by_symbol = {e["instrument"]["symbol"]: e for e in body["entries"]}
    assert by_symbol["DEMO"]["held"] is True and by_symbol["DEMO"]["trend"] in ("favorable", "defavorable", "neutre")
    assert by_symbol["DEMO"]["valuation"] == "indisponible"  # nothing cached yet, and no call made
    assert by_symbol["WATCH"]["watched"] is True and by_symbol["WATCH"]["trend"] == "indisponible"
    assert by_symbol["WATCH"]["rsi"] is not None and by_symbol["WATCH"]["observations"] == 40


def test_portfolio_checkup_and_targets(registered_user, db_session):
    client, csrf, _ = registered_user
    a = _shared_instrument(db_session, "CA")
    b = _shared_instrument(db_session, "CB")
    _seed_bars(db_session, a.id, n=300, seed=1)
    _seed_bars(db_session, b.id, n=300, seed=2)
    portfolio = client.post("/api/v1/portfolios", json={"name": "Check"}, headers=_h(csrf)).json()
    pid = portfolio["id"]
    when = (datetime.now(UTC) - timedelta(days=200)).isoformat()
    client.post(
        f"/api/v1/portfolios/{pid}/transactions",
        json={"type": "depot", "trade_date": when, "quantity": "1", "unit_price": "5000", "currency": "EUR"},
        headers=_h(csrf),
    )
    for inst, qty in ((a, "30"), (b, "10")):
        resp = client.post(
            f"/api/v1/portfolios/{pid}/transactions",
            json={
                "instrument_id": inst.id,
                "type": "achat",
                "trade_date": when,
                "quantity": qty,
                "unit_price": "100",
                "currency": "EUR",
            },
            headers=_h(csrf),
        )
        assert resp.status_code == 201, resp.text

    body = client.get(f"/api/v1/portfolios/{pid}/checkup").json()
    keys = {s["key"]: s for s in body["signals"]}
    assert keys["nombre_lignes"]["reading"] == "defavorable" and keys["nombre_lignes"]["value"] == "2"
    assert "concentration_instrument" in keys and "correlation_moyenne" in keys
    assert "volatilite_portefeuille" in keys and "drawdown_portefeuille" in keys
    assert body["has_targets"] is False and "ecart_cible" not in keys
    labels = {a["label"] for a in body["allocation"]}
    assert labels == {"action", "tresorerie"}

    bad = client.patch(
        f"/api/v1/portfolios/{pid}/targets", json={"target_allocation": {"action": 0.5}}, headers=_h(csrf)
    )
    assert bad.status_code == 422
    bad_key = client.patch(f"/api/v1/portfolios/{pid}/targets", json={"target_allocation": {"or": 1}}, headers=_h(csrf))
    assert bad_key.status_code == 422
    ok = client.patch(
        f"/api/v1/portfolios/{pid}/targets",
        json={"target_allocation": {"action": 0.5, "tresorerie": 0.5}},
        headers=_h(csrf),
    )
    assert ok.status_code == 200 and ok.json()["target_allocation"] == {"action": 0.5, "tresorerie": 0.5}
    assert client.get(f"/api/v1/portfolios/{pid}").json()["target_allocation"] == {"action": 0.5, "tresorerie": 0.5}

    body = client.get(f"/api/v1/portfolios/{pid}/checkup").json()
    keys = {s["key"]: s for s in body["signals"]}
    assert body["has_targets"] is True and keys["ecart_cible"]["reading"] in ("favorable", "neutre", "defavorable")
    action = next(x for x in body["allocation"] if x["label"] == "action")
    assert action["target"] == 0.5 and action["drift"] is not None

    cleared = client.patch(f"/api/v1/portfolios/{pid}/targets", json={"target_allocation": None}, headers=_h(csrf))
    assert cleared.json()["target_allocation"] is None


def test_decision_endpoints_are_tenant_scoped(registered_user, client, db_session):
    http, csrf, _ = registered_user
    portfolio = http.post("/api/v1/portfolios", json={"name": "P"}, headers=_h(csrf)).json()
    private = http.post(
        "/api/v1/instruments",
        json={"symbol": "MINE", "name": "Mine", "asset_class": "action", "currency": "EUR"},
        headers=_h(csrf),
    ).json()
    http.post("/api/v1/auth/logout", headers=_h(csrf))
    csrf2, _ = register(http, "bob@example.com")
    assert http.get(f"/api/v1/portfolios/{portfolio['id']}/checkup").status_code == 404
    assert http.get(f"/api/v1/instruments/{private['id']}/decision-aid").status_code == 404
    assert (
        http.patch(
            f"/api/v1/portfolios/{portfolio['id']}/targets", json={"target_allocation": None}, headers=_h(csrf2)
        ).status_code
        == 404
    )
    assert http.get("/api/v1/market/decision-overview").json()["entries"] == []


def test_prediction_reading_appears_after_an_experiment(registered_user, db_session):
    client, csrf, _ = registered_user
    instrument = _shared_instrument(db_session, "PRED")
    _seed_bars(db_session, instrument.id, n=400, seed=9)
    created = client.post(
        "/api/v1/prediction/experiments",
        json={"instrument_id": instrument.id, "name": "x", "config": {"horizon_days": 5}, "run_now": True},
        headers=_h(csrf),
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "completed"
    body = client.get(f"/api/v1/instruments/{instrument.id}/decision-aid").json()
    assert body["prediction_available"] is True
    pred = next(s for s in body["signals"] if s["key"] == "prediction")
    assert pred["family"] == "prediction" and "expérimental" in pred["label"].lower()
    assert db_session.scalar(select(OhlcBar.id).where(OhlcBar.instrument_id == instrument.id).limit(1)) is not None
