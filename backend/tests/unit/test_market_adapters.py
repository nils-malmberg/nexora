"""Contract tests for the market adapters against recorded (synthetic)
provider payloads - every HTTP call is intercepted by respx, so nothing
here ever reaches a real provider (specs/TESTING.md, specs/DATA_SOURCES.md:
'contract tests fournisseurs')."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from app.market import http as market_http
from app.market.base import (
    MarketMisconfigured,
    MarketNotFound,
    MarketNotSupported,
    MarketRateLimited,
    MarketUnavailable,
)
from app.market.coingecko import CoinGeckoProvider
from app.market.finnhub import FinnhubProvider
from app.market.frankfurter import FrankfurterProvider
from app.market.ratelimit import TokenBucket, TTLCache
from app.market.yahoo import YahooProvider

# --- token bucket ----------------------------------------------------------------


def test_token_bucket_refuses_past_burst_then_refills(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("app.market.ratelimit.time.monotonic", lambda: clock[0])
    bucket = TokenBucket(per_minute=60, burst=2)
    assert bucket.take() and bucket.take()
    assert not bucket.take()  # burst exhausted, no waiting: caller serves cache instead
    clock[0] += 1.0  # 60/min = 1 token per second
    assert bucket.take()
    assert not bucket.take()


def test_ttl_cache_expires(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("app.market.ratelimit.time.monotonic", lambda: clock[0])
    cache = TTLCache(ttl_seconds=10)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    clock[0] = 11
    assert cache.get("k") is None


def test_local_budget_exhaustion_raises_rate_limited_without_network():
    bucket = market_http.bucket_for("yahoo")
    while bucket.take():
        pass
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get("https://query2.finance.yahoo.com/v1/finance/search")
        with pytest.raises(MarketRateLimited) as exc:
            YahooProvider().search("apple")
        assert exc.value.remote is False
        assert not route.called  # the request never left the process


# --- error mapping -----------------------------------------------------------------


@respx.mock
def test_http_429_maps_to_remote_rate_limited():
    respx.get("https://query2.finance.yahoo.com/v1/finance/search").mock(return_value=httpx.Response(429))
    with pytest.raises(MarketRateLimited) as exc:
        YahooProvider().search("apple")
    assert exc.value.remote is True


@respx.mock
def test_http_5xx_maps_to_unavailable_and_timeout_too():
    respx.get("https://api.coingecko.com/api/v3/search").mock(return_value=httpx.Response(503))
    with pytest.raises(MarketUnavailable):
        CoinGeckoProvider().search("bit")
    respx.get("https://api.coingecko.com/api/v3/simple/price").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(MarketUnavailable):
        CoinGeckoProvider().quote("bitcoin")


@respx.mock
def test_http_403_maps_to_not_supported():
    respx.get("https://api.frankfurter.dev/v1/latest").mock(return_value=httpx.Response(403))
    with pytest.raises(MarketNotSupported):
        FrankfurterProvider().latest("USD", ["EUR"])


# --- Yahoo -----------------------------------------------------------------------------


YAHOO_SEARCH = {
    "quotes": [
        {
            "symbol": "AAPL",
            "shortname": "Apple Inc.",
            "longname": "Apple Inc.",
            "quoteType": "EQUITY",
            "exchDisp": "NASDAQ",
        },
        {"symbol": "CW8.PA", "shortname": "AMUNDI MSCI WORLD", "quoteType": "ETF", "exchDisp": "Paris"},
        {"symbol": "BTC-USD", "shortname": "Bitcoin USD", "quoteType": "CRYPTOCURRENCY", "exchDisp": "CCC"},
        {"symbol": "AAPL260117C00200000", "quoteType": "OPTION"},
    ]
}

YAHOO_CHART = {
    "chart": {
        "result": [
            {
                "meta": {
                    "currency": "USD",
                    "symbol": "AAPL",
                    "exchangeName": "NMS",
                    "regularMarketPrice": 231.45,
                    "regularMarketTime": 1768507200,
                    "chartPreviousClose": 229.1,
                },
                "timestamp": [1768334400, 1768420800, 1768507200],
                "indicators": {
                    "quote": [
                        {
                            "open": [228.0, 229.5, None],
                            "high": [230.0, 231.0, None],
                            "low": [227.1, 228.7, None],
                            "close": [229.1, 230.2, None],
                            "volume": [50000000, 48000000, None],
                        }
                    ]
                },
            }
        ],
        "error": None,
    }
}


@respx.mock
def test_yahoo_search_maps_quote_types_and_drops_unsupported():
    respx.get("https://query2.finance.yahoo.com/v1/finance/search").mock(
        return_value=httpx.Response(200, json=YAHOO_SEARCH)
    )
    results = YahooProvider().search("a")
    assert [(r.symbol, r.asset_class) for r in results] == [
        ("AAPL", "action"),
        ("CW8.PA", "etf"),
        ("BTC-USD", "crypto"),
    ]
    assert results[0].exchange == "NASDAQ"
    assert results[0].currency is None  # only known from the chart meta


@respx.mock
def test_yahoo_quote_and_history_skip_null_rows():
    respx.get("https://query2.finance.yahoo.com/v8/finance/chart/AAPL").mock(
        return_value=httpx.Response(200, json=YAHOO_CHART)
    )
    provider = YahooProvider()
    quote = provider.quote("AAPL")
    assert quote is not None
    assert quote.price == Decimal("231.45")
    assert quote.currency == "USD"
    assert quote.as_of == datetime.fromtimestamp(1768507200, tz=UTC)
    assert quote.is_delayed is True
    assert quote.previous_close == Decimal("229.1")
    assert "Yahoo" in quote.license_note

    history = provider.history("AAPL", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 20, tzinfo=UTC))
    assert history.has_ohlc is True
    assert [b.close for b in history.bars] == [
        Decimal("229.1"),
        Decimal("230.2"),
    ]  # the null row is dropped, never invented
    assert history.bars[0].volume == Decimal("50000000")
    assert history.bars[0].as_of.hour == 0


@respx.mock
def test_yahoo_unknown_symbol_is_not_found():
    respx.get("https://query2.finance.yahoo.com/v8/finance/chart/NOPE").mock(
        return_value=httpx.Response(
            200, json={"chart": {"result": None, "error": {"code": "Not Found", "description": "No data"}}}
        )
    )
    with pytest.raises(MarketNotFound):
        YahooProvider().quote("NOPE")


# --- CoinGecko ---------------------------------------------------------------------


@respx.mock
def test_coingecko_search_quote_and_close_only_history(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", "demo-key-value")
    search_route = respx.get("https://api.coingecko.com/api/v3/search").mock(
        return_value=httpx.Response(200, json={"coins": [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"}]})
    )
    respx.get("https://api.coingecko.com/api/v3/simple/price").mock(
        return_value=httpx.Response(200, json={"bitcoin": {"usd": 65123.456789, "last_updated_at": 1768507200}})
    )
    respx.get("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart").mock(
        return_value=httpx.Response(
            200,
            json={
                "prices": [
                    [1768348800000, 63000.0],
                    [1768435200000, 64000.0],
                    [1768521600000, 65000.0],
                    [1768530000000, 65100.0],
                ],
                "total_volumes": [[1768348800000, 2.5e10], [1768435200000, 2.6e10], [1768521600000, 2.4e10]],
            },
        )
    )
    provider = CoinGeckoProvider()
    results = provider.search("bit")
    assert results[0].symbol == "BTC" and results[0].provider_symbol == "bitcoin" and results[0].currency == "USD"
    assert search_route.calls[0].request.headers["x-cg-demo-api-key"] == "demo-key-value"

    quote = provider.quote("bitcoin")
    assert quote.price == Decimal("65123.456789") and quote.currency == "USD"

    history = provider.history("bitcoin", datetime(2026, 1, 10, tzinfo=UTC), datetime(2026, 1, 20, tzinfo=UTC))
    assert history.has_ohlc is False
    assert [b.close for b in history.bars] == [
        Decimal("63000.0"),
        Decimal("64000.0"),
        Decimal("65000.0"),
    ]  # intraday dup dropped
    assert all(b.open is None for b in history.bars)
    assert history.bars[0].volume == Decimal("25000000000.0")


@respx.mock
def test_coingecko_unknown_id_is_not_found():
    respx.get("https://api.coingecko.com/api/v3/simple/price").mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(MarketNotFound):
        CoinGeckoProvider().quote("not-a-coin")


# --- Finnhub -----------------------------------------------------------------------------


def test_finnhub_without_key_is_misconfigured(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with pytest.raises(MarketMisconfigured):
        FinnhubProvider().search("apple")
    assert FinnhubProvider().health().healthy is False


@respx.mock
def test_finnhub_quote_sends_token_in_query_and_never_in_logs(monkeypatch, capsys):
    monkeypatch.setenv("FINNHUB_API_KEY", "sekrit-finnhub-key")
    quote_route = respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json={"c": 231.45, "pc": 229.1, "t": 1768507200})
    )
    respx.get("https://finnhub.io/api/v1/stock/profile2").mock(
        return_value=httpx.Response(200, json={"currency": "USD"})
    )
    quote = FinnhubProvider().quote("AAPL")
    assert quote.price == Decimal("231.45") and quote.currency == "USD"
    assert quote_route.calls[0].request.url.params["token"] == "sekrit-finnhub-key"
    assert "sekrit-finnhub-key" not in capsys.readouterr().out


@respx.mock
def test_finnhub_candles_restricted_plan_is_not_supported(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    respx.get("https://finnhub.io/api/v1/stock/candle").mock(return_value=httpx.Response(403))
    with pytest.raises(MarketNotSupported):
        FinnhubProvider().history("AAPL", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 20, tzinfo=UTC))


# --- Frankfurter ---------------------------------------------------------------------


@respx.mock
def test_frankfurter_latest_and_series():
    respx.get("https://api.frankfurter.dev/v1/latest").mock(
        return_value=httpx.Response(
            200, json={"base": "USD", "date": "2026-01-15", "rates": {"EUR": 0.9213, "GBP": 0.79}}
        )
    )
    respx.get("https://api.frankfurter.dev/v1/2026-01-12..2026-01-15").mock(
        return_value=httpx.Response(
            200,
            json={
                "base": "USD",
                "rates": {"2026-01-12": {"EUR": 0.92}, "2026-01-13": {"EUR": 0.921}, "2026-01-15": {"EUR": 0.9213}},
            },
        )
    )
    provider = FrankfurterProvider()
    day, rates = provider.latest("USD", ["EUR", "GBP"])
    assert day == datetime(2026, 1, 15, tzinfo=UTC)
    assert rates["EUR"] == Decimal("0.9213")
    series = provider.series("USD", "EUR", datetime(2026, 1, 12, tzinfo=UTC), datetime(2026, 1, 15, tzinfo=UTC))
    assert len(series) == 3  # the 14th (holiday) is simply absent, not interpolated
    assert series[datetime(2026, 1, 13, tzinfo=UTC)] == Decimal("0.921")


@respx.mock
def test_finnhub_fundamentals_converts_percents_and_reads_consensus(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    respx.get("https://finnhub.io/api/v1/stock/metric").mock(
        return_value=httpx.Response(
            200,
            json={
                "metric": {
                    "peTTM": 28.4,
                    "pbQuarterly": 45.1,
                    "dividendYieldIndicatedAnnual": 0.55,
                    "epsGrowthTTMYoy": 9.8,
                    "roeTTM": 150.2,
                    "netProfitMarginTTM": 25.3,
                    "totalDebt/totalEquityQuarterly": 1.72,
                    "beta": 1.24,
                    "52WeekHigh": 260.1,
                    "52WeekLow": 169.2,
                    "marketCapitalization": 3400000,
                },
                "metricType": "all",
                "symbol": "AAPL",
            },
        )
    )
    respx.get("https://finnhub.io/api/v1/stock/recommendation").mock(
        return_value=httpx.Response(
            200,
            json=[{"buy": 20, "hold": 10, "sell": 2, "strongBuy": 12, "strongSell": 1, "period": "2026-09-01"}],
        )
    )
    f = FinnhubProvider().fundamentals("AAPL")
    assert f.pe == Decimal("28.4") and f.pb == Decimal("45.1")
    assert f.dividend_yield == Decimal("0.0055") and f.roe == Decimal("1.502")
    assert f.net_margin == Decimal("0.253") and f.debt_to_equity == Decimal("1.72")
    assert (f.analyst_buy, f.analyst_hold, f.analyst_sell, f.analyst_period) == (32, 10, 3, "2026-09-01")
    assert f.as_dict()["pe"] == "28.40000000" and f.source == "finnhub"


@respx.mock
def test_finnhub_fundamentals_without_recommendation_and_empty_metric(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    respx.get("https://finnhub.io/api/v1/stock/metric").mock(
        return_value=httpx.Response(200, json={"metric": {"peTTM": 12.0}, "symbol": "X"})
    )
    respx.get("https://finnhub.io/api/v1/stock/recommendation").mock(return_value=httpx.Response(500))
    f = FinnhubProvider().fundamentals("X")
    assert f.pe == Decimal("12") and f.analyst_buy is None
    respx.get("https://finnhub.io/api/v1/stock/metric").mock(return_value=httpx.Response(200, json={"metric": {}}))
    with pytest.raises(MarketNotFound):
        FinnhubProvider().fundamentals("NOPE")
