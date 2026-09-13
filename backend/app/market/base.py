"""Market-data provider contract (specs/DATA_SOURCES.md "Contrat fournisseur").

Every adapter returns typed results carrying `source`, `retrieved_at`,
`as_of`, delay flag and `license_note`, and raises one of the typed errors
below instead of a library exception — so app/market/service.py applies one
cache / rate-limit / circuit-breaker policy to all of them. Adapters never
touch the database and never fabricate a value: a missing price is `None`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


class MarketDataError(Exception):
    """Base class for provider failures."""


class MarketUnavailable(MarketDataError):
    """Network/HTTP/parse failure — the provider could not answer."""


class MarketRateLimited(MarketDataError):
    """Refused locally (token bucket) or remotely (HTTP 429)."""

    def __init__(self, message: str, remote: bool = False):
        super().__init__(message)
        self.remote = remote


class MarketNotFound(MarketDataError):
    """The provider does not know this symbol."""


class MarketNotSupported(MarketDataError):
    """The provider (or its free tier) does not offer this capability."""


class MarketMisconfigured(MarketDataError):
    """A required credential/env var is missing."""


@dataclass
class SearchResult:
    symbol: str
    name: str
    asset_class: str
    provider: str
    provider_symbol: str
    currency: str | None = None
    exchange: str | None = None
    isin: str | None = None


@dataclass
class Quote:
    price: Decimal
    currency: str
    as_of: datetime
    source: str
    retrieved_at: datetime
    is_delayed: bool = True
    license_note: str = ""
    previous_close: Decimal | None = None
    exchange: str | None = None


@dataclass
class Bar:
    as_of: datetime
    close: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    volume: Decimal | None = None


@dataclass
class HistoryResult:
    bars: list[Bar]
    currency: str
    source: str
    retrieved_at: datetime
    granularity: str = "1d"
    license_note: str = ""
    has_ohlc: bool = True


@dataclass
class Fundamentals:
    """Company fundamentals as published by the provider (all optional —
    an ETF or a crypto-asset has none). Ratios are plain fractions
    (0.035 = 3.5 %), never percents, so every reader applies one convention."""

    as_of: datetime
    source: str
    license_note: str = ""
    pe: Decimal | None = None
    pb: Decimal | None = None
    dividend_yield: Decimal | None = None
    eps_growth: Decimal | None = None
    revenue_growth: Decimal | None = None
    roe: Decimal | None = None
    net_margin: Decimal | None = None
    debt_to_equity: Decimal | None = None
    beta: Decimal | None = None
    market_cap: Decimal | None = None
    week52_high: Decimal | None = None
    week52_low: Decimal | None = None
    analyst_buy: int | None = None
    analyst_hold: int | None = None
    analyst_sell: int | None = None
    analyst_period: str | None = None

    def as_dict(self) -> dict:
        out = {}
        for key, value in self.__dict__.items():
            if isinstance(value, Decimal):
                out[key] = str(value)
            elif isinstance(value, datetime):
                out[key] = value.isoformat()
            else:
                out[key] = value
        return out


@dataclass
class HealthStatus:
    healthy: bool
    detail: str


@dataclass
class ProviderCapabilities:
    search: bool
    quote: bool
    history: bool
    ohlc: bool
    asset_classes: tuple[str, ...]
    real_time: bool = False
    attribution: str = ""
    license_note: str = ""
    extra: dict = field(default_factory=dict)


class MarketDataProvider(ABC):
    name: str = "abstract"

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[SearchResult]: ...

    @abstractmethod
    def quote(self, provider_symbol: str) -> Quote | None: ...

    @abstractmethod
    def history(self, provider_symbol: str, start: datetime, end: datetime) -> HistoryResult: ...

    def fundamentals(self, provider_symbol: str) -> Fundamentals | None:
        """Optional capability (`capabilities.extra["fundamentals"]`)."""
        raise MarketNotSupported(f"{self.name}: fundamentals not offered")

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="no health probe implemented")


class FxProvider(ABC):
    name: str = "abstract-fx"
    license_note: str = ""
    attribution: str = ""

    @abstractmethod
    def latest(self, base: str, quotes: list[str]) -> tuple[datetime, dict[str, Decimal]]: ...

    @abstractmethod
    def series(self, base: str, quote: str, start: datetime, end: datetime) -> dict[datetime, Decimal]: ...

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="no health probe implemented")


_QUANTUM = Decimal("0.00000001")


def to_decimal(value) -> Decimal | None:
    """Provider JSON floats carry binary noise (168.25999450683594 for a
    168.26 close): normalise to 8 decimals at the boundary so the noise
    never reaches a computation or a screen."""
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(_QUANTUM)
    except (ArithmeticError, ValueError):
        return None
