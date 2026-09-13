"""CoinGecko adapter (crypto-assets) — public API, no key required.

Terms: free tier is for personal/non-commercial use with attribution
("Powered by CoinGecko"), ~10–30 calls/min shared per IP with strict 429s;
our local budget stays far below that. An optional demo key
(`COINGECKO_API_KEY`, sent as `x-cg-demo-api-key`) raises the quota — its
*value* is only read from the environment at call time, never stored.

Quotes and history are requested in USD: crypto instruments live in the
shared catalog with currency USD and are converted to each portfolio's base
currency through the FX layer, like any foreign-currency instrument. The
daily market chart publishes closes and volumes only, so bars carry no
open/high/low (drawn as a line, never as invented candles).
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
    MarketNotFound,
    ProviderCapabilities,
    Quote,
    SearchResult,
    to_decimal,
)
from app.market.http import get_json

BASE_URL = "https://api.coingecko.com/api/v3"
VS_CURRENCY = "usd"
LICENSE_NOTE = (
    "CoinGecko (API publique gratuite) — usage personnel, attribution « Powered by CoinGecko » requise, "
    "quotas partagés par adresse IP."
)


class CoinGeckoProvider(MarketDataProvider):
    name = "coingecko"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            search=True,
            quote=True,
            history=True,
            ohlc=False,
            asset_classes=("crypto",),
            real_time=False,
            attribution="Powered by CoinGecko",
            license_note=LICENSE_NOTE,
        )

    def _headers(self) -> dict:
        key = os.environ.get(settings.coingecko_api_key_env_var)
        return {"x-cg-demo-api-key": key} if key else {}

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        payload = get_json(self.name, f"{BASE_URL}/search", params={"query": query}, headers=self._headers())
        coins = payload.get("coins", []) if isinstance(payload, dict) else []
        results: list[SearchResult] = []
        for coin in coins:
            coin_id = coin.get("id")
            symbol = (coin.get("symbol") or "").upper()
            if not coin_id or not symbol:
                continue
            results.append(
                SearchResult(
                    symbol=symbol,
                    name=coin.get("name") or symbol,
                    asset_class="crypto",
                    provider=self.name,
                    provider_symbol=coin_id,
                    currency=VS_CURRENCY.upper(),
                    exchange="CoinGecko",
                )
            )
        return results[:limit]

    def quote(self, provider_symbol: str) -> Quote | None:
        payload = get_json(
            self.name,
            f"{BASE_URL}/simple/price",
            params={
                "ids": provider_symbol,
                "vs_currencies": VS_CURRENCY,
                "include_last_updated_at": "true",
                "precision": "full",
            },
            headers=self._headers(),
        )
        entry = payload.get(provider_symbol) if isinstance(payload, dict) else None
        if not entry:
            raise MarketNotFound(f"coingecko: {provider_symbol} not found")
        price = to_decimal(entry.get(VS_CURRENCY))
        ts = entry.get("last_updated_at")
        if price is None:
            return None
        return Quote(
            price=price,
            currency=VS_CURRENCY.upper(),
            as_of=datetime.fromtimestamp(int(ts), tz=UTC) if ts else datetime.now(UTC),
            source=self.name,
            retrieved_at=datetime.now(UTC),
            is_delayed=True,
            license_note=LICENSE_NOTE,
        )

    def history(self, provider_symbol: str, start: datetime, end: datetime) -> HistoryResult:
        days = max(1, (end - start).days + 1)
        payload = get_json(
            self.name,
            f"{BASE_URL}/coins/{provider_symbol}/market_chart",
            params={"vs_currency": VS_CURRENCY, "days": str(min(days, 3650)), "interval": "daily"},
            headers=self._headers(),
        )
        prices = payload.get("prices", []) if isinstance(payload, dict) else []
        volumes = {int(v[0]) // 86_400_000: to_decimal(v[1]) for v in payload.get("total_volumes", []) or []}
        bars: list[Bar] = []
        seen_days: set[int] = set()
        for point in prices:
            ts_ms, price = point[0], point[1]
            day_key = int(ts_ms) // 86_400_000
            if day_key in seen_days:
                continue  # the last point can be intraday for "today"; keep the first (daily) sample
            seen_days.add(day_key)
            close = to_decimal(price)
            if close is None:
                continue
            bars.append(
                Bar(
                    as_of=datetime.fromtimestamp(day_key * 86_400, tz=UTC),
                    close=close,
                    volume=volumes.get(day_key),
                )
            )
        bars = [b for b in bars if start.date() <= b.as_of.date() <= end.date()]
        return HistoryResult(
            bars=bars,
            currency=VS_CURRENCY.upper(),
            source=self.name,
            retrieved_at=datetime.now(UTC),
            license_note=LICENSE_NOTE,
            has_ohlc=False,
        )

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="configured (public API, no key required)")
