from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.csv_import import (
    compute_fingerprint,
    parse_csv,
    parse_date,
    parse_decimal,
    sniff_delimiter,
    sniff_encoding,
    suggest_column_mapping,
)


def test_sniff_encoding_utf8():
    assert sniff_encoding("héllo,wörld".encode()) in ("utf_8", "utf-8", "UTF-8-SIG")


def test_sniff_delimiter_semicolon():
    assert sniff_delimiter("date;type;symbol\n2026-01-01;achat;AAA") == ";"


def test_sniff_delimiter_comma():
    assert sniff_delimiter("date,type,symbol\n2026-01-01,achat,AAA") == ","


def test_parse_csv_produces_rows_keyed_by_header():
    headers, rows = parse_csv("date,type\n2026-01-01,achat\n2026-01-02,vente", ",")
    assert headers == ["date", "type"]
    assert rows == [{"date": "2026-01-01", "type": "achat"}, {"date": "2026-01-02", "type": "vente"}]


def test_suggest_column_mapping_matches_synonyms():
    mapping = suggest_column_mapping(
        ["Date", "Type", "Symbole inconnu", "Quantité", "Prix unitaire", "Devise", "Frais"]
    )
    assert mapping["date"] == "Date"
    assert mapping["type"] == "Type"
    assert mapping["quantity"] == "Quantité"
    assert mapping["unit_price"] == "Prix unitaire"
    assert mapping["currency"] == "Devise"
    assert mapping["fees"] == "Frais"
    assert "symbol" not in mapping  # "Symbole inconnu" isn't a recognized synonym


def test_parse_decimal_handles_french_comma_decimal():
    assert parse_decimal("12,5", "quantity") == Decimal("12.5")


def test_parse_decimal_handles_thousands_and_decimal_comma():
    assert parse_decimal("1.234,56", "unit_price") == Decimal("1234.56")


def test_parse_decimal_invalid_raises():
    with pytest.raises(ValueError, match="invalide"):
        parse_decimal("not-a-number", "quantity")


def test_parse_date_iso():
    assert parse_date("2026-01-15", "UTC") == datetime(2026, 1, 15, tzinfo=UTC)


def test_parse_date_french_format():
    assert parse_date("15/01/2026", "UTC") == datetime(2026, 1, 15, tzinfo=UTC)


def test_parse_date_applies_default_timezone_to_naive_value():
    result = parse_date("2026-01-15 10:00:00", "Europe/Paris")
    assert result == datetime(2026, 1, 15, 9, 0, 0, tzinfo=UTC)


def test_parse_date_invalid_raises():
    with pytest.raises(ValueError, match="invalide"):
        parse_date("not-a-date", "UTC")


def test_parse_date_unknown_timezone_raises():
    with pytest.raises(ValueError, match="fuseau"):
        parse_date("2026-01-15", "Not/AZone")


def test_compute_fingerprint_is_stable_and_sensitive_to_fields():
    base_kwargs = dict(
        portfolio_id="p1",
        type_="achat",
        trade_date=datetime(2026, 1, 1, tzinfo=UTC),
        instrument_key="i1",
        quantity=Decimal("10"),
        unit_price=Decimal("100"),
        currency="EUR",
        fees=Decimal("0"),
        account=None,
    )
    assert compute_fingerprint(**base_kwargs) == compute_fingerprint(**base_kwargs)
    changed = {**base_kwargs, "quantity": Decimal("11")}
    assert compute_fingerprint(**base_kwargs) != compute_fingerprint(**changed)
