"""Broker export profiles: detection by headers and row rewriting. Samples
are synthetic but follow the column layout of each app's export."""

from __future__ import annotations

from app.domain.broker_presets import PRESETS, SKIP_KEY, apply_preset, describe_presets, detect_preset

REVOLUT_HEADERS = ["Date", "Ticker", "Type", "Quantity", "Price per share", "Total Amount", "Currency", "FX Rate"]
REVOLUT_ROWS = [
    {
        "Date": "2026-01-05T14:32:10.123Z",
        "Ticker": "",
        "Type": "CASH TOP-UP",
        "Quantity": "",
        "Price per share": "",
        "Total Amount": "$1,000.00",
        "Currency": "USD",
        "FX Rate": "1.09",
    },
    {
        "Date": "2026-01-06T15:01:00.000Z",
        "Ticker": "AAPL",
        "Type": "BUY - MARKET",
        "Quantity": "2.5",
        "Price per share": "$190.10",
        "Total Amount": "$475.25",
        "Currency": "USD",
        "FX Rate": "1.09",
    },
    {
        "Date": "2026-02-10T12:00:00.000Z",
        "Ticker": "AAPL",
        "Type": "DIVIDEND",
        "Quantity": "",
        "Price per share": "",
        "Total Amount": "$0.62",
        "Currency": "USD",
        "FX Rate": "1.08",
    },
    {
        "Date": "2026-03-01T08:00:00.000Z",
        "Ticker": "",
        "Type": "CUSTODY FEE",
        "Quantity": "",
        "Price per share": "",
        "Total Amount": "-$0.12",
        "Currency": "USD",
        "FX Rate": "1.08",
    },
    {
        "Date": "2026-03-02T15:30:00.000Z",
        "Ticker": "AAPL",
        "Type": "SELL - LIMIT",
        "Quantity": "1",
        "Price per share": "$200.00",
        "Total Amount": "$200.00",
        "Currency": "USD",
        "FX Rate": "1.08",
    },
    {
        "Date": "2026-03-03T15:30:00.000Z",
        "Ticker": "AAPL",
        "Type": "STOCK SPLIT",
        "Quantity": "4",
        "Price per share": "",
        "Total Amount": "",
        "Currency": "USD",
        "FX Rate": "1.08",
    },
]

TR_HEADERS = ["Datum", "Typ", "Wert", "Notiz", "ISIN", "Anzahl", "Gebühren", "Steuern"]
TR_ROWS = [
    {
        "Datum": "02.01.2026",
        "Typ": "Einzahlung",
        "Wert": "500,00",
        "Notiz": "SEPA",
        "ISIN": "",
        "Anzahl": "",
        "Gebühren": "",
        "Steuern": "",
    },
    {
        "Datum": "03.01.2026",
        "Typ": "Kauf",
        "Wert": "-101,00",
        "Notiz": "Demo SA",
        "ISIN": "FR0000000001",
        "Anzahl": "2",
        "Gebühren": "1,00",
        "Steuern": "",
    },
    {
        "Datum": "15.02.2026",
        "Typ": "Dividende",
        "Wert": "3,40",
        "Notiz": "Demo SA",
        "ISIN": "FR0000000001",
        "Anzahl": "2",
        "Gebühren": "",
        "Steuern": "0,60",
    },
    {
        "Datum": "01.03.2026",
        "Typ": "Zinsen",
        "Wert": "1,25",
        "Notiz": "Zinsen Februar",
        "ISIN": "",
        "Anzahl": "",
        "Gebühren": "",
        "Steuern": "",
    },
    {
        "Datum": "10.03.2026",
        "Typ": "Verkauf",
        "Wert": "89,00",
        "Notiz": "Demo SA",
        "ISIN": "FR0000000001",
        "Anzahl": "1",
        "Gebühren": "1,00",
        "Steuern": "",
    },
    {
        "Datum": "11.03.2026",
        "Typ": "Aktiensplit",
        "Wert": "",
        "Notiz": "",
        "ISIN": "FR0000000001",
        "Anzahl": "4",
        "Gebühren": "",
        "Steuern": "",
    },
]


def test_detection_by_headers_not_by_name():
    assert detect_preset(REVOLUT_HEADERS).key == "revolut"
    assert detect_preset(TR_HEADERS).key == "trade_republic"
    assert detect_preset(["Date", "Type", "Value", "Note", "ISIN", "Shares", "Fees", "Tax"]).key == "trade_republic"
    assert detect_preset(["date", "type", "symbol", "quantity", "unit_price", "currency"]) is None
    assert {p["key"] for p in describe_presets()} == set(PRESETS)
    assert all(p["instructions"] for p in describe_presets())


def test_revolut_rows_become_canonical_transactions():
    rows = apply_preset("revolut", REVOLUT_ROWS, REVOLUT_HEADERS)
    assert [r.get("type") for r in rows] == ["depot", "achat", "dividende", "frais", "vente", None]
    assert rows[0]["unit_price"] == "1000" and rows[0]["quantity"] == "1" and rows[0]["symbol"] == ""
    assert rows[1] == {
        **rows[1],
        "symbol": "AAPL",
        "quantity": "2.5",
        "unit_price": "190.1",
        "currency": "USD",
        "asset_class": "action",
    }
    assert rows[2]["unit_price"] == "0.62" and rows[2]["symbol"] == "AAPL"
    assert rows[3]["unit_price"] == "0.12"  # sign normalised, currency symbol stripped
    assert rows[4]["type"] == "vente" and rows[4]["unit_price"] == "200"
    assert "STOCK SPLIT" in rows[5][SKIP_KEY]  # reported, never guessed


def test_trade_republic_rows_use_isin_and_back_out_fees():
    rows = apply_preset("trade_republic", TR_ROWS, TR_HEADERS)
    assert [r.get("type") for r in rows] == ["depot", "achat", "dividende", "interet", "vente", None]
    assert rows[0]["unit_price"] == "500" and rows[0]["currency"] == "EUR" and rows[0]["isin"] == ""
    buy = rows[1]
    assert buy["isin"] == "FR0000000001" and buy["symbol"] == "" and buy["quantity"] == "2"
    assert buy["unit_price"] == "50"  # (101 - 1 fee) / 2
    assert buy["fees"] == "1"
    dividend = rows[2]
    assert dividend["unit_price"] == "3.4" and dividend["fees"] == "0.6"  # withholding tax kept as a fee
    assert rows[3]["type"] == "interet" and rows[3]["unit_price"] == "1.25"
    sell = rows[4]
    assert sell["unit_price"] == "90"  # (89 + 1 fee) / 1
    assert "Aktiensplit" in rows[5][SKIP_KEY]
