"""Offline providers: `NullProvider` (never answers — the safe default when
live data is disabled) and `FixtureProvider` / `FixtureFxProvider` (committed
synthetic JSON, for tests and the docker "demo" profile). Neither makes a
network call, so the whole test suite and the demo run with zero external
dependencies (specs/TESTING.md: "Aucun test ne dépend d'un service externe").
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from app.market.base import (
    Bar,
    Fundamentals,
    FxProvider,
    HealthStatus,
    HistoryResult,
    MarketDataProvider,
    MarketNotFound,
    ProviderCapabilities,
    Quote,
    SearchResult,
    to_decimal,
)


class NullProvider(MarketDataProvider):
    name = "null"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(search=False, quote=False, history=False, ohlc=False, asset_classes=())

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        return []

    def quote(self, provider_symbol: str) -> Quote | None:
        return None

    def history(self, provider_symbol: str, start: datetime, end: datetime) -> HistoryResult:
        return HistoryResult(bars=[], currency="", source=self.name, retrieved_at=datetime.now(UTC))

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=False, detail="live market data disabled (manual prices only)")


class FixtureProvider(MarketDataProvider):
    """Fixture format (see tests/fixtures/market_data/demo_quotes.json):
    {"<provider_symbol>": {"name", "asset_class", "currency", "exchange",
    "price", "as_of", "history": [{"as_of", "open", "high", "low", "close",
    "volume"}]}}. `open/high/low/volume` may be omitted (close-only bars)."""

    name = "fixture"

    def __init__(self, fixture_path: Path):
        self._path = fixture_path
        self._data: dict = json.loads(fixture_path.read_text(encoding="utf-8")) if fixture_path.exists() else {}

    def fundamentals(self, provider_symbol: str) -> Fundamentals | None:
        entry = self._data.get(provider_symbol)
        if entry is None:
            raise MarketNotFound(f"fixture: unknown symbol {provider_symbol}")
        raw = entry.get("fundamentals")
        if not raw:
            raise MarketNotFound(f"fixture: no fundamentals for {provider_symbol}")
        analyst_keys = ("analyst_buy", "analyst_hold", "analyst_sell", "analyst_period")
        fields = {k: to_decimal(v) for k, v in raw.items() if k not in analyst_keys}
        return Fundamentals(
            as_of=datetime.now(UTC),
            source=self.name,
            license_note="Fixture locale, aucune donnée réelle.",
            analyst_buy=raw.get("analyst_buy"),
            analyst_hold=raw.get("analyst_hold"),
            analyst_sell=raw.get("analyst_sell"),
            analyst_period=raw.get("analyst_period"),
            **fields,
        )

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            search=True,
            quote=True,
            history=True,
            ohlc=True,
            asset_classes=("action", "etf", "crypto", "indice", "devise"),
            attribution="Données synthétiques (fixture locale)",
            license_note="Fixture locale, aucune donnée réelle.",
            extra={"fundamentals": True},
        )

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        q = query.lower()
        out = []
        for symbol, entry in self._data.items():
            isin = str(entry.get("isin", "")).lower()
            if q in symbol.lower() or q in str(entry.get("name", "")).lower() or (isin and q == isin):
                out.append(
                    SearchResult(
                        symbol=symbol,
                        name=entry.get("name", symbol),
                        asset_class=entry.get("asset_class", "action"),
                        provider=self.name,
                        provider_symbol=symbol,
                        currency=entry.get("currency"),
                        exchange=entry.get("exchange"),
                        isin=entry.get("isin"),
                    )
                )
        return out[:limit]

    def quote(self, provider_symbol: str) -> Quote | None:
        entry = self._data.get(provider_symbol)
        if entry is None:
            raise MarketNotFound(f"fixture: {provider_symbol} not found")
        if "price" not in entry:
            return None
        return Quote(
            price=Decimal(str(entry["price"])),
            currency=entry["currency"],
            as_of=datetime.fromisoformat(entry["as_of"]),
            source=self.name,
            retrieved_at=datetime.now(UTC),
            is_delayed=True,
            license_note="Fixture locale.",
        )

    def history(self, provider_symbol: str, start: datetime, end: datetime) -> HistoryResult:
        entry = self._data.get(provider_symbol)
        if entry is None:
            raise MarketNotFound(f"fixture: {provider_symbol} not found")
        bars = []
        has_ohlc = True
        for point in entry.get("history", []):
            as_of = datetime.fromisoformat(point["as_of"])
            if not (start <= as_of <= end):
                continue
            close = to_decimal(point.get("close", point.get("price")))
            if close is None:
                continue
            if point.get("open") is None:
                has_ohlc = False
            bars.append(
                Bar(
                    as_of=as_of,
                    close=close,
                    open=to_decimal(point.get("open")),
                    high=to_decimal(point.get("high")),
                    low=to_decimal(point.get("low")),
                    volume=to_decimal(point.get("volume")),
                )
            )
        return HistoryResult(
            bars=bars,
            currency=entry.get("currency", "EUR"),
            source=self.name,
            retrieved_at=datetime.now(UTC),
            has_ohlc=has_ohlc,
        )

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail=f"fixture data from {self._path.name}")


class FixtureFxProvider(FxProvider):
    """`{"USD": {"EUR": 0.92, ...}, ...}` — one flat table used for every date."""

    name = "fixture-fx"
    license_note = "Fixture locale, aucun taux réel."

    def __init__(self, table: dict[str, dict[str, str]] | None = None):
        self._table = table or {}

    def latest(self, base: str, quotes: list[str]) -> tuple[datetime, dict[str, Decimal]]:
        row = self._table.get(base, {})
        rates = {q: Decimal(str(row[q])) for q in quotes if q in row}
        if not rates:
            raise MarketNotFound(f"fixture-fx: no rate for {base}")
        return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0), rates

    def series(self, base: str, quote: str, start: datetime, end: datetime) -> dict[datetime, Decimal]:
        row = self._table.get(base, {})
        if quote not in row:
            return {}
        rate = Decimal(str(row[quote]))
        out: dict[datetime, Decimal] = {}
        day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        while day <= end:
            out[day] = rate
            day = day + timedelta(days=1)
        return out


class NullFxProvider(FxProvider):
    name = "null-fx"

    def latest(self, base: str, quotes: list[str]) -> tuple[datetime, dict[str, Decimal]]:
        raise MarketNotFound("fx disabled")

    def series(self, base: str, quote: str, start: datetime, end: datetime) -> dict[datetime, Decimal]:
        return {}

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=False, detail="fx conversion disabled")
