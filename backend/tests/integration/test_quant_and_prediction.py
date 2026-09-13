"""Quant toolbox and prediction endpoints on a synthetic daily series
inserted directly as OhlcBar rows (no provider involved)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np

from app.config import settings
from app.models import Instrument, OhlcBar
from tests.conftest import auth_headers, register


def _headers(csrf):
    return auth_headers(csrf)


def _seed_bars(db_session, instrument_id: str, n: int = 400, seed: int = 1, currency: str = "EUR") -> list[float]:
    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n)))
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=n)
    rows = []
    for i, close in enumerate(closes):
        c = Decimal(str(round(float(close), 4)))
        rows.append(
            OhlcBar(
                instrument_id=instrument_id,
                interval="1d",
                as_of=start + timedelta(days=i),
                open=c * Decimal("0.995"),
                high=c * Decimal("1.01"),
                low=c * Decimal("0.99"),
                close=c,
                volume=Decimal(10000),
                currency=currency,
                source="fixture",
            )
        )
    db_session.add_all(rows)
    db_session.commit()
    return [float(c) for c in closes]


def _shared_instrument(db_session, symbol="SYN", currency="EUR") -> Instrument:
    instrument = Instrument(
        symbol=symbol,
        name=f"Synthetic {symbol}",
        asset_class="action",
        currency=currency,
        provider="fixture",
        provider_symbol=symbol,
    )
    db_session.add(instrument)
    db_session.commit()
    return instrument


def _portfolio_with(client, csrf, instrument_ids, quantities):
    portfolio = client.post(
        "/api/v1/portfolios", json={"name": "Quant", "base_currency": "EUR"}, headers=_headers(csrf)
    ).json()
    for instrument_id, qty in zip(instrument_ids, quantities, strict=True):
        resp = client.post(
            f"/api/v1/portfolios/{portfolio['id']}/transactions",
            json={
                "instrument_id": instrument_id,
                "type": "achat",
                "trade_date": (datetime.now(UTC) - timedelta(days=200)).isoformat(),
                "quantity": str(qty),
                "unit_price": "100",
                "currency": "EUR",
            },
            headers=_headers(csrf),
        )
        assert resp.status_code == 201, resp.text
    return portfolio


# --- quant ----------------------------------------------------------------------


def test_instrument_stats_var_drawdown_and_montecarlo(registered_user, db_session):
    client, csrf, _ = registered_user
    instrument = _shared_instrument(db_session)
    _seed_bars(db_session, instrument.id)

    stats = client.get("/api/v1/quant/stats", params={"instrument_id": instrument.id, "days": 365}).json()
    assert stats["has_sufficient_data"] and stats["subject"] == f"instrument:{instrument.id}"
    assert stats["volatility_annualized"] > 0 and stats["observations"] > 300
    assert "annualisation" in stats["method"]

    var = client.get(
        "/api/v1/quant/var", params={"instrument_id": instrument.id, "confidence": 0.99, "horizon": 5}
    ).json()
    assert var["has_sufficient_data"] and var["historical_var"] > 0 and var["confidence"] == 0.99

    dd = client.get("/api/v1/quant/drawdown", params={"instrument_id": instrument.id}).json()
    assert dd["max_drawdown"] <= 0 and len(dd["points"]) == dd["observations"]

    mc = client.get(
        "/api/v1/quant/montecarlo",
        params={"instrument_id": instrument.id, "horizon": 30, "simulations": 200, "seed": 1},
    ).json()
    assert mc["has_sufficient_data"] and len(mc["percentiles"]["50"]) == 31
    assert "prévision" in mc["disclaimer"]


def test_quant_requires_a_subject_and_hides_other_users_instruments(registered_user, db_session):
    client, csrf, _ = registered_user
    assert client.get("/api/v1/quant/stats").status_code == 422
    _, bob_id = register(client, email="bob@example.com")
    private = Instrument(
        user_id=bob_id, symbol="PRIV", name="Private", asset_class="actif_prive", currency="EUR", provider="manual"
    )
    db_session.add(private)
    db_session.commit()
    client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "correct horse battery staple"})
    assert client.get("/api/v1/quant/stats", params={"instrument_id": private.id}).status_code == 404


def test_portfolio_correlation_frontier_and_capm(registered_user, db_session):
    client, csrf, _ = registered_user
    a = _shared_instrument(db_session, "AAA")
    b = _shared_instrument(db_session, "BBB")
    bench = _shared_instrument(db_session, "IDX")
    _seed_bars(db_session, a.id, seed=1)
    _seed_bars(db_session, b.id, seed=2)
    _seed_bars(db_session, bench.id, seed=3)
    portfolio = _portfolio_with(client, csrf, [a.id, b.id], [10, 5])

    corr = client.get(f"/api/v1/portfolios/{portfolio['id']}/quant/correlation").json()
    assert corr["has_sufficient_data"] and corr["labels"] == ["AAA", "BBB"]
    assert abs(corr["matrix"][0][0] - 1) < 1e-9 and corr["matrix"][0][1] == corr["matrix"][1][0]

    frontier = client.get(f"/api/v1/portfolios/{portfolio['id']}/quant/frontier", params={"points": 8}).json()
    assert frontier["has_sufficient_data"] and len(frontier["frontier"]) == 8
    assert frontier["current"] is not None and abs(sum(frontier["current"]["weights"]) - 1) < 1e-6
    assert "recommandée" in frontier["disclaimer"]

    capm = client.get(
        "/api/v1/quant/capm", params={"portfolio_id": portfolio["id"], "benchmark_instrument_id": bench.id}
    ).json()
    assert capm["benchmark"] == "IDX" and capm["has_sufficient_data"]
    assert capm["beta"] is not None and -1 <= capm["correlation"] <= 1

    # Portfolio-level stats use the valuation history (real dates: the daily bars).
    stats = client.get("/api/v1/quant/stats", params={"portfolio_id": portfolio["id"], "days": 180}).json()
    assert stats["has_sufficient_data"] and stats["currency"] == "EUR"


def test_indicators_include_extended_set_on_ohlc(registered_user, db_session):
    client, csrf, _ = registered_user
    instrument = _shared_instrument(db_session)
    _seed_bars(db_session, instrument.id, n=80)
    body = client.get(f"/api/v1/instruments/{instrument.id}/indicators", params={"bollinger": 20, "atr": 14}).json()
    assert body["has_ohlc"] is True
    assert (
        len(body["bollinger_upper"]) == 80
        and body["bollinger_upper"][19] is not None
        and body["bollinger_upper"][18] is None
    )
    assert body["atr"][13] is not None and body["stochastic_k"][13] is not None and body["obv"][-1] is not None
    assert body["bollinger_k"] == 2.0


# --- prediction -------------------------------------------------------------------


def test_prediction_experiment_lifecycle(registered_user, db_session):
    client, csrf, _ = registered_user
    instrument = _shared_instrument(db_session)
    _seed_bars(db_session, instrument.id, n=400)

    status = client.get("/api/v1/prediction/status").json()
    assert status["enabled"] is True and "ridge" in status["available_models"]

    created = client.post(
        "/api/v1/prediction/experiments",
        json={
            "instrument_id": instrument.id,
            "name": "SYN h5",
            "config": {"horizon": 5, "n_folds": 3, "models": ["naive_last", "ridge"], "min_train": 120},
        },
        headers=_headers(csrf),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "completed", body.get("error")  # synchronous in the test environment
    assert body["dataset_hash"] and body["code_version"].startswith("pred-")
    assert set(body["metrics"]["models"]) == {"naive_last", "ridge", "meta"}
    assert body["metrics"]["models"]["naive_last"]["rmse_vs_naive"] == 1.0
    assert len(body["folds"]) >= 2 and body["latest_forecast"]["horizon"] == 5
    assert "conseil" in body["disclaimer"]

    listed = client.get("/api/v1/prediction/experiments").json()
    assert [e["name"] for e in listed] == ["SYN h5"] and listed[0]["instrument_symbol"] == "SYN"

    rerun = client.post(f"/api/v1/prediction/experiments/{body['id']}/run", headers=_headers(csrf))
    assert rerun.status_code == 200 and rerun.json()["status"] == "completed"
    assert rerun.json()["metrics"] == body["metrics"]  # reproducible

    # Tenant isolation + delete.
    bob_csrf, _ = register(client, email="bob@example.com")
    assert client.get(f"/api/v1/prediction/experiments/{body['id']}").status_code == 404
    assert client.delete(f"/api/v1/prediction/experiments/{body['id']}", headers=_headers(bob_csrf)).status_code == 404


def test_prediction_refuses_short_history(registered_user, db_session):
    client, csrf, _ = registered_user
    instrument = _shared_instrument(db_session)
    _seed_bars(db_session, instrument.id, n=50)
    created = client.post(
        "/api/v1/prediction/experiments",
        json={"instrument_id": instrument.id, "name": "too short"},
        headers=_headers(csrf),
    ).json()
    assert created["status"] == "failed" and "insufficient history" in created["error"]


def test_prediction_kill_switch(registered_user, monkeypatch):
    client, csrf, _ = registered_user
    monkeypatch.setattr(settings, "prediction_enabled", False)
    assert client.get("/api/v1/prediction/status").json()["enabled"] is False
    assert client.get("/api/v1/prediction/experiments").status_code == 503
    resp = client.post(
        "/api/v1/prediction/experiments", json={"instrument_id": "x", "name": "n"}, headers=_headers(csrf)
    )
    assert resp.status_code == 503


def test_prediction_rejects_unknown_model(registered_user, db_session):
    client, csrf, _ = registered_user
    instrument = _shared_instrument(db_session)
    resp = client.post(
        "/api/v1/prediction/experiments",
        json={"instrument_id": instrument.id, "name": "bad", "config": {"models": ["lstm-magic"]}},
        headers=_headers(csrf),
    )
    assert resp.status_code == 422


def test_auto_experiment_is_reused_within_the_day(registered_user, db_session):
    client, csrf, _ = registered_user
    instrument = _shared_instrument(db_session, "AUTO")
    _seed_bars(db_session, instrument.id, n=400, seed=12)
    first = client.post(f"/api/v1/prediction/auto/{instrument.id}", params={"horizon": 5}, headers=_headers(csrf))
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["name"] == "auto-5j" and body["status"] == "completed" and body["latest_forecast"]
    again = client.post(f"/api/v1/prediction/auto/{instrument.id}", params={"horizon": 5}, headers=_headers(csrf))
    assert again.json()["id"] == body["id"]
    other = client.post(f"/api/v1/prediction/auto/{instrument.id}", params={"horizon": 10}, headers=_headers(csrf))
    assert other.json()["id"] != body["id"] and other.json()["name"] == "auto-10j"
    # The decision aid picks the prediction up (config key "horizon").
    aid = client.get(f"/api/v1/instruments/{instrument.id}/decision-aid").json()
    pred = next(s for s in aid["signals"] if s["key"] == "prediction")
    assert "10 j" in pred["label"] or "5 j" in pred["label"]


def test_chart_tools_endpoint(registered_user, db_session):
    client, csrf, _ = registered_user
    instrument = _shared_instrument(db_session, "TOOLS")
    _seed_bars(db_session, instrument.id, n=300, seed=8)
    resp = client.get(f"/api/v1/instruments/{instrument.id}/chart-tools", params={"days": 400})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_ohlc"] is True and len(body["dates"]) == 300
    assert len(body["ichimoku"]["tenkan"]) == 300 and len(body["ichimoku"]["future_dates"]) == 26
    assert body["ichimoku"]["reading"] and body["sar"]["reading"]
    assert [p["period"] for p in body["pivots"]] == ["jour", "semaine", "mois"]
    assert body["pivots"][0]["s3"] < body["pivots"][0]["pivot"] < body["pivots"][0]["r3"]
    assert body["fibonacci"]["direction"] in ("hausse", "baisse") and len(body["fibonacci"]["levels"]) == 7
    assert isinstance(body["supports"], list) and isinstance(body["resistances"], list)
    for pattern in body["patterns"]:
        assert pattern["name"] and pattern["direction"] in ("haussier", "baissier", "indecision")

    private = client.post(
        "/api/v1/instruments",
        json={"symbol": "CLS", "name": "Close only", "asset_class": "crypto", "currency": "EUR"},
        headers=_headers(csrf),
    ).json()
    from app.models import OhlcBar as Bar

    start = datetime.now(UTC) - timedelta(days=40)
    for i in range(40):
        db_session.add(
            Bar(
                instrument_id=private["id"],
                as_of=start + timedelta(days=i),
                close=Decimal(100 + i),
                currency="EUR",
                source="manual",
            )
        )
    db_session.commit()
    body = client.get(f"/api/v1/instruments/{private['id']}/chart-tools").json()
    assert body["has_ohlc"] is False and body["ichimoku"] is None and body["sar"] is None and body["pivots"] == []
    assert body["fibonacci"]["direction"] == "hausse"
