"""MarketDataProvider interface.

No real adapter is wired in this PR: choosing and configuring a real live
provider (equity quotes and/or FX rates) requires the same license/ToS
verification and explicit user confirmation this project already applied to
the News & Events module's SEC EDGAR / Finnhub sources — see
specs/DATA_SOURCES.md. Until then, every price shown to a user comes only
from a manually entered PricePoint (or, in a later PR, CSV import): never a
live network call, never a fabricated value.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path


@dataclass
class Quote:
    symbol: str
    price: Decimal
    currency: str
    as_of: datetime


@dataclass
class HealthStatus:
    healthy: bool
    detail: str


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote | None: ...

    @abstractmethod
    def get_history(self, symbol: str, start: datetime, end: datetime) -> list[Quote]: ...

    @abstractmethod
    def health(self) -> HealthStatus: ...

    def capabilities(self) -> dict:
        return {"history": True, "real_time": False}


class NullMarketDataProvider(MarketDataProvider):
    """The default. Never fabricates a quote — see module docstring."""

    name = "null"

    def get_quote(self, symbol: str) -> Quote | None:
        return None

    def get_history(self, symbol: str, start: datetime, end: datetime) -> list[Quote]:
        return []

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=False, detail="no market data provider configured")


class FixtureMarketDataProvider(MarketDataProvider):
    """Reads quotes from a committed local JSON fixture — for local demos and
    tests only, never a real network call. Mirrors the News & Events module's
    `demo` profile (synthetic data served without any external dependency)."""

    name = "fixture"

    def __init__(self, fixture_path: Path):
        self._fixture_path = fixture_path
        self._data = json.loads(fixture_path.read_text(encoding="utf-8")) if fixture_path.exists() else {}

    def get_quote(self, symbol: str) -> Quote | None:
        entry = self._data.get(symbol)
        if entry is None:
            return None
        return Quote(
            symbol=symbol,
            price=Decimal(str(entry["price"])),
            currency=entry["currency"],
            as_of=datetime.fromisoformat(entry["as_of"]),
        )

    def get_history(self, symbol: str, start: datetime, end: datetime) -> list[Quote]:
        entry = self._data.get(symbol)
        if entry is None:
            return []
        return [
            Quote(
                symbol=symbol,
                price=Decimal(str(point["price"])),
                currency=entry["currency"],
                as_of=datetime.fromisoformat(point["as_of"]),
            )
            for point in entry.get("history", [])
            if start <= datetime.fromisoformat(point["as_of"]) <= end
        ]

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail=f"fixture data from {self._fixture_path.name}")


def get_active_provider() -> MarketDataProvider:
    """No configuration flag to select a real provider exists yet - there is
    none to select. Returns the safe default."""
    return NullMarketDataProvider()
