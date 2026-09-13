"""Yahoo Finance–compatible adapter (the "fournisseur gratuit de type Yahoo
Finance" of specs/README.md), via the public JSON chart/search endpoints —
no HTML scraping, no cookies, no account.

License / caveats (surfaced to the user as `license_note`): this is an
undocumented API intended for Yahoo's own site; data is for personal,
non-commercial use, may be delayed by 15+ minutes depending on the exchange,
must not be redistributed, and can change or stop without notice. The
adapter is interchangeable (see app/market/registry.py) precisely because of
that fragility.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.market.base import (
    Bar,
    HealthStatus,
    HistoryResult,
    MarketDataProvider,
    MarketNotFound,
    MarketUnavailable,
    ProviderCapabilities,
    Quote,
    SearchResult,
    to_decimal,
)
from app.market.http import get_json

SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"

LICENSE_NOTE = (
    "Yahoo Finance (API non officielle) — usage personnel uniquement, données possiblement différées "
    "(15 min ou plus selon la place), pas de redistribution ; peut cesser de fonctionner sans préavis."
)

_QUOTE_TYPE_TO_CLASS = {
    "EQUITY": "action",
    "ETF": "etf",
    "MUTUALFUND": "etf",
    "CRYPTOCURRENCY": "crypto",
    "INDEX": "indice",
    "CURRENCY": "devise",
}


class YahooProvider(MarketDataProvider):
    name = "yahoo"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            search=True,
            quote=True,
            history=True,
            ohlc=True,
            asset_classes=("action", "etf", "indice", "devise", "crypto"),
            real_time=False,
            attribution="Données : Yahoo Finance",
            license_note=LICENSE_NOTE,
        )

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        payload = get_json(
            self.name,
            SEARCH_URL,
            params={"q": query, "quotesCount": limit, "newsCount": 0, "listsCount": 0, "enableFuzzyQuery": "false"},
        )
        results: list[SearchResult] = []
        for entry in payload.get("quotes", []) if isinstance(payload, dict) else []:
            symbol = entry.get("symbol")
            quote_type = entry.get("quoteType")
            asset_class = _QUOTE_TYPE_TO_CLASS.get(quote_type or "")
            if not symbol or asset_class is None:
                continue
            results.append(
                SearchResult(
                    symbol=symbol,
                    name=entry.get("longname") or entry.get("shortname") or symbol,
                    asset_class=asset_class,
                    provider=self.name,
                    provider_symbol=symbol,
                    currency=None,  # only known from the chart meta; resolved on first quote
                    exchange=entry.get("exchDisp") or entry.get("exchange"),
                )
            )
        return results[:limit]

    def _chart(self, symbol: str, params: dict) -> dict:
        payload = get_json(self.name, CHART_URL.format(symbol=symbol), params=params)
        chart = payload.get("chart") if isinstance(payload, dict) else None
        if not chart:
            raise MarketUnavailable("yahoo: unexpected chart payload")
        error = chart.get("error")
        if error:
            code = str(error.get("code", ""))
            if code.lower() in ("not found", "not_found"):
                raise MarketNotFound(f"yahoo: {symbol} not found")
            raise MarketUnavailable(f"yahoo: {code}")
        result = chart.get("result") or []
        if not result:
            raise MarketNotFound(f"yahoo: {symbol} not found")
        return result[0]

    def quote(self, provider_symbol: str) -> Quote | None:
        result = self._chart(provider_symbol, {"range": "5d", "interval": "1d", "includePrePost": "false"})
        meta = result.get("meta") or {}
        price = to_decimal(meta.get("regularMarketPrice"))
        currency = meta.get("currency")
        ts = meta.get("regularMarketTime")
        if price is None or not currency or ts is None:
            return None
        return Quote(
            price=price,
            currency=currency,
            as_of=datetime.fromtimestamp(int(ts), tz=UTC),
            source=self.name,
            retrieved_at=datetime.now(UTC),
            is_delayed=True,
            license_note=LICENSE_NOTE,
            previous_close=to_decimal(meta.get("chartPreviousClose")),
            exchange=meta.get("exchangeName"),
        )

    def history(self, provider_symbol: str, start: datetime, end: datetime) -> HistoryResult:
        period1 = int(start.timestamp())
        period2 = int((end + timedelta(days=1)).timestamp())
        result = self._chart(
            provider_symbol,
            {
                "period1": period1,
                "period2": period2,
                "interval": "1d",
                "includePrePost": "false",
                "events": "div,splits",
            },
        )
        meta = result.get("meta") or {}
        currency = meta.get("currency") or "USD"
        timestamps = result.get("timestamp") or []
        quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        opens, highs, lows = quotes.get("open") or [], quotes.get("high") or [], quotes.get("low") or []
        closes, volumes = quotes.get("close") or [], quotes.get("volume") or []

        bars: list[Bar] = []
        for i, ts in enumerate(timestamps):
            close = to_decimal(closes[i] if i < len(closes) else None)
            if close is None:
                continue  # Yahoo emits null rows for holidays/gaps: never invent a bar there
            bars.append(
                Bar(
                    as_of=datetime.fromtimestamp(int(ts), tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0),
                    open=to_decimal(opens[i] if i < len(opens) else None),
                    high=to_decimal(highs[i] if i < len(highs) else None),
                    low=to_decimal(lows[i] if i < len(lows) else None),
                    close=close,
                    volume=to_decimal(volumes[i] if i < len(volumes) else None),
                )
            )
        # Yahoo's last bar of the day is a live, still-moving candle: keep it
        # (the freshest information we have) but the sync layer re-fetches the
        # tail so it converges to the settled close.
        return HistoryResult(
            bars=bars,
            currency=currency,
            source=self.name,
            retrieved_at=datetime.now(UTC),
            license_note=LICENSE_NOTE,
            has_ohlc=True,
        )

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="configured (unofficial API, best effort)")


__all__ = ["YahooProvider", "LICENSE_NOTE", "Decimal"]
