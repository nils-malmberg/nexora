"""Broker exports end to end: detection, ISIN resolution through the (fixture)
market provider, preview report and commit."""

from __future__ import annotations

import csv
import io

from tests.conftest import auth_headers
from tests.unit.test_broker_presets import REVOLUT_HEADERS, REVOLUT_ROWS, TR_HEADERS, TR_ROWS


def _csv(headers, rows, delimiter=","):
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row[h] for h in headers])
    return out.getvalue().encode("utf-8")


def _portfolio(client, csrf, currency="EUR"):
    return client.post(
        "/api/v1/portfolios", json={"name": "Courtier", "base_currency": currency}, headers=auth_headers(csrf)
    ).json()


def _upload(client, csrf, portfolio_id, content, name="export.csv"):
    resp = client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        files={"file": (name, content, "text/csv")},
        headers=auth_headers(csrf),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_presets_endpoint_lists_instructions(registered_user):
    client, csrf, _ = registered_user
    body = client.get("/api/v1/portfolios/x/imports/presets").json()
    assert {p["key"] for p in body} == {"trade_republic", "revolut"}
    assert all(len(p["instructions"]) >= 2 for p in body)


def test_revolut_export_is_detected_previewed_and_committed(registered_user):
    client, csrf, _ = registered_user
    portfolio = _portfolio(client, csrf, "USD")
    job = _upload(client, csrf, portfolio["id"], _csv(REVOLUT_HEADERS, REVOLUT_ROWS))
    assert job["preset"] == "revolut" and job["preset_label"].startswith("Revolut")
    assert job["headers"] == [
        "date",
        "type",
        "symbol",
        "isin",
        "asset_class",
        "quantity",
        "unit_price",
        "currency",
        "fees",
        "note",
    ]
    assert job["sample_rows"][1]["type"] == "achat"

    preview = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/imports/{job['id']}/preview", json={}, headers=auth_headers(csrf)
    ).json()
    statuses = [r["status"] for r in preview["rows"]]
    assert statuses == ["valid", "valid", "valid", "valid", "valid", "error"]
    assert "ligne ignorée" in preview["rows"][5]["messages"][0]
    assert "sera créé automatiquement" in preview["rows"][1]["messages"][0]  # AAPL unknown here -> private instrument

    committed = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/imports/{job['id']}/commit", headers=auth_headers(csrf)
    ).json()
    assert committed["inserted_count"] == 5 and committed["error_count"] == 1
    valuation = client.get(f"/api/v1/portfolios/{portfolio['id']}/valuation").json()
    assert valuation["positions"][0]["symbol"] == "AAPL" and valuation["positions"][0]["quantity"] == "1.50000000"
    # cash: +1000 - 475.25 + 0.62 - 0.12 + 200 = 725.25
    assert valuation["cash"] == "725.250000"
    txs = client.get(f"/api/v1/portfolios/{portfolio['id']}/transactions").json()["items"]
    assert {t["type"] for t in txs} == {"depot", "achat", "dividende", "frais", "vente"}
    assert any(t["note"] == "CUSTODY FEE" for t in txs)


def test_trade_republic_export_resolves_isin_through_catalog(registered_user):
    client, csrf, _ = registered_user
    portfolio = _portfolio(client, csrf)
    job = _upload(client, csrf, portfolio["id"], _csv(TR_HEADERS, TR_ROWS, delimiter=";"), name="trade-republic.csv")
    assert job["preset"] == "trade_republic"

    preview = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/imports/{job['id']}/preview", json={}, headers=auth_headers(csrf)
    ).json()
    # FR0000000001 is DEMO in the fixture provider: resolved with one search and added to the shared catalog.
    assert preview["resolved_isins"] == {"FR0000000001": "DEMO"}
    statuses = [r["status"] for r in preview["rows"]]
    assert statuses == ["valid", "valid", "valid", "valid", "valid", "error"]
    assert preview["rows"][1]["canonical"]["symbol"] == "DEMO"
    instrument = client.get("/api/v1/market/search", params={"q": "FR0000000001"}).json()["candidates"][0]
    assert instrument["in_catalog"] and instrument["symbol"] == "DEMO"

    committed = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/imports/{job['id']}/commit", headers=auth_headers(csrf)
    ).json()
    assert committed["inserted_count"] == 5
    valuation = client.get(f"/api/v1/portfolios/{portfolio['id']}/valuation").json()
    assert valuation["positions"][0]["symbol"] == "DEMO" and valuation["positions"][0]["quantity"] == "1.00000000"
    # cash: 500 - 101 (100 + 1 fee) + 3.40 - 0.60 + 1.25 + 89 (90 - 1 fee) = 492.05
    assert valuation["cash"] == "492.050000"
    assert valuation["positions"][0]["price_source"] == "fixture"  # priced by the catalog provider


def test_unknown_isin_is_reported_not_guessed(registered_user):
    client, csrf, _ = registered_user
    portfolio = _portfolio(client, csrf)
    rows = [dict(TR_ROWS[1], ISIN="DE0000000009")]
    job = _upload(client, csrf, portfolio["id"], _csv(TR_HEADERS, rows, delimiter=";"))
    preview = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/imports/{job['id']}/preview", json={}, headers=auth_headers(csrf)
    ).json()
    assert preview["resolved_isins"] == {}
    assert preview["rows"][0]["status"] == "error"
    assert "ISIN DE0000000009 introuvable" in preview["rows"][0]["messages"][0]


def test_preset_can_be_overridden_to_generic(registered_user):
    client, csrf, _ = registered_user
    portfolio = _portfolio(client, csrf, "USD")
    job = _upload(client, csrf, portfolio["id"], _csv(REVOLUT_HEADERS, REVOLUT_ROWS))
    preview = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/imports/{job['id']}/preview",
        json={
            "preset": "",
            "column_mapping": {
                "date": "Date",
                "type": "Type",
                "symbol": "Ticker",
                "quantity": "Quantity",
                "unit_price": "Price per share",
                "currency": "Currency",
            },
        },
        headers=auth_headers(csrf),
    ).json()
    assert preview["preset"] is None
    assert (
        client.post(
            f"/api/v1/portfolios/{portfolio['id']}/imports/{job['id']}/preview",
            json={"preset": "bogus"},
            headers=auth_headers(csrf),
        ).status_code
        == 422
    )


def test_generic_csv_accepts_broker_labels_and_new_types(registered_user):
    client, csrf, _ = registered_user
    portfolio = _portfolio(client, csrf)
    content = b"date;type;symbol;quantity;unit_price;currency\n2026-01-02;Deposit;;1;100;EUR\n2026-01-03;Interest;;1;0,5;EUR\n2026-01-04;Fee;;1;0,2;EUR\n"
    job = _upload(client, csrf, portfolio["id"], content)
    assert job["preset"] is None
    preview = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/imports/{job['id']}/preview", json={}, headers=auth_headers(csrf)
    ).json()
    assert [r["canonical"]["type"] for r in preview["rows"]] == ["depot", "interet", "frais"]
    assert all(r["status"] == "valid" for r in preview["rows"])
    client.post(f"/api/v1/portfolios/{portfolio['id']}/imports/{job['id']}/commit", headers=auth_headers(csrf))
    assert client.get(f"/api/v1/portfolios/{portfolio['id']}/valuation").json()["cash"] == "100.300000"
