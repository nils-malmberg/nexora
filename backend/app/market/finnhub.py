"""Finnhub adapter (equities) — alternative to Yahoo, requires a free API key
referenced by env var name (`FINNHUB_API_KEY` by default). Free tier: ~60
calls/min, personal use; `/search`, `/quote` and `/stock/profile2` are free,
while `/stock/candle` (history) is restricted on the free plan — reported as
`MarketNotSupported` rather than silently returning nothing.

specs/DATA_SOURCES.md already documents this provider for company news; the
same key serves both.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from app.config import settings
from app.market.base import (
    Bar,
    HealthStatus,
    HistoryResult,
    MarketDataProvider,
    MarketMisconfigured,
    MarketNotFound,
    MarketNotSupported,
    ProviderCapabilities,
    Quote,
    SearchResult,
    to_decimal,
)
from app.market.http import get_json

BASE_URL = "https://finnhub.io/api/v1"
LICENSE_NOTE = "Finnhub (offre gratuite, clé personnelle) — usage personnel/non commercial, ~60 appels/min."

_TYPE_TO_CLASS = {"Common Stock": "action", "ETP": "etf", "ETF": "etf", "ADR": "action", "REIT": "action"}


class FinnhubProvider(MarketDataProvider):
    name = "finnhub"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            search=True,
            quote=True,
            history=True,
            ohlc=True,
            asset_classes=("action", "etf"),
            real_time=False,
            attribution="Données : Finnhub",
            license_note=LICENSE_NOTE,
        )

    def _token(self) -> str:
        key = os.environ.get(settings.finnhub_api_key_env_var)
        if not key:
            raise MarketMisconfigured(f"finnhub: environment variable {settings.finnhub_api_key_env_var} is not set")
        return key

    def _get(self, path: str, params: dict) -> dict | list:
        return get_json(self.name, f"{BASE_URL}{path}", params={**params, "token": self._token()})

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        payload = self._get("/search", {"q": query})
        results: list[SearchResult] = []
        for entry in payload.get("result", []) if isinstance(payload, dict) else []:
            symbol = entry.get("symbol")
            if not symbol:
                continue
            results.append(
                SearchResult(
                    symbol=symbol,
                    name=entry.get("description") or symbol,
                    asset_class=_TYPE_TO_CLASS.get(entry.get("type") or "", "action"),
                    provider=self.name,
                    provider_symbol=symbol,
                    currency=None,
                )
            )
        return results[:limit]

    def _currency(self, symbol: str) -> str | None:
        profile = self._get("/stock/profile2", {"symbol": symbol})
        return profile.get("currency") if isinstance(profile, dict) else None

    def quote(self, provider_symbol: str) -> Quote | None:
        payload = self._get("/quote", {"symbol": provider_symbol})
        if not isinstance(payload, dict):
            return None
        price = to_decimal(payload.get("c"))
        ts = payload.get("t")
        if price is None or price == 0 or not ts:
            raise MarketNotFound(f"finnhub: no quote for {provider_symbol}")
        currency = self._currency(provider_symbol) or "USD"
        return Quote(
            price=price,
            currency=currency,
            as_of=datetime.fromtimestamp(int(ts), tz=UTC),
            source=self.name,
            retrieved_at=datetime.now(UTC),
            is_delayed=True,
            license_note=LICENSE_NOTE,
            previous_close=to_decimal(payload.get("pc")),
        )

    def history(self, provider_symbol: str, start: datetime, end: datetime) -> HistoryResult:
        payload = self._get(
            "/stock/candle",
            {"symbol": provider_symbol, "resolution": "D", "from": int(start.timestamp()), "to": int(end.timestamp())},
        )
        if not isinstance(payload, dict) or payload.get("s") == "no_data":
            return HistoryResult(bars=[], currency="USD", source=self.name, retrieved_at=datetime.now(UTC))
        if payload.get("s") != "ok":
            raise MarketNotSupported("finnhub: candles unavailable on this plan")
        bars: list[Bar] = []
        for i, ts in enumerate(payload.get("t", [])):
            close = to_decimal(payload["c"][i])
            if close is None:
                continue
            bars.append(
                Bar(
                    as_of=datetime.fromtimestamp(int(ts), tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0),
                    open=to_decimal(payload["o"][i]),
                    high=to_decimal(payload["h"][i]),
                    low=to_decimal(payload["l"][i]),
                    close=close,
                    volume=to_decimal(payload["v"][i]),
                )
            )
        return HistoryResult(
            bars=bars, currency="USD", source=self.name, retrieved_at=datetime.now(UTC), license_note=LICENSE_NOTE
        )

    def health(self) -> HealthStatus:
        if not os.environ.get(settings.finnhub_api_key_env_var):
            return HealthStatus(healthy=False, detail=f"{settings.finnhub_api_key_env_var} not set")
        return HealthStatus(healthy=True, detail="key configured")
