from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.adapters.market_data import FixtureMarketDataProvider, NullMarketDataProvider, get_active_provider

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "market_data" / "demo_quotes.json"


def test_null_provider_never_returns_data():
    provider = NullMarketDataProvider()
    assert provider.get_quote("ANYTHING") is None
    assert provider.get_history("ANYTHING", datetime.now(UTC), datetime.now(UTC)) == []
    assert provider.health().healthy is False


def test_get_active_provider_defaults_to_null():
    assert isinstance(get_active_provider(), NullMarketDataProvider)


def test_fixture_provider_returns_quote():
    provider = FixtureMarketDataProvider(FIXTURE_PATH)
    quote = provider.get_quote("DEMO")
    assert quote is not None
    assert quote.price == Decimal("42.5")
    assert quote.currency == "EUR"
    assert provider.health().healthy is True


def test_fixture_provider_unknown_symbol_returns_none():
    provider = FixtureMarketDataProvider(FIXTURE_PATH)
    assert provider.get_quote("UNKNOWN") is None


def test_fixture_provider_history_filters_by_date_range():
    provider = FixtureMarketDataProvider(FIXTURE_PATH)
    history = provider.get_history(
        "DEMO",
        datetime(2026, 1, 14, tzinfo=UTC),
        datetime(2026, 1, 15, 23, tzinfo=UTC),
    )
    assert len(history) == 2
