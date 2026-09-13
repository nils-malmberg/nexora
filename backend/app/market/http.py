"""One outbound HTTP path for every market adapter: rate-limited, timed,
metered, and mapped to the typed errors in app/market/base.py.

Secrets travel in query params or headers here and nowhere else; the
structured logger redacts `token=`/`apikey=`-style values, and httpx's own
per-request logging is silenced (see app/observability/logging.py).
"""

from __future__ import annotations

import time

import httpx

from app.config import settings
from app.market.base import MarketDataError, MarketNotFound, MarketNotSupported, MarketRateLimited, MarketUnavailable
from app.market.ratelimit import TokenBucket
from app.observability.logging import get_logger, log_event
from app.observability.metrics import market_rate_limited_total, market_request_latency_seconds, market_requests_total

logger = get_logger(__name__)

_buckets: dict[str, TokenBucket] = {}


def bucket_for(provider: str) -> TokenBucket:
    if provider not in _buckets:
        per_minute = {
            "yahoo": settings.yahoo_rate_limit_per_minute,
            "coingecko": settings.coingecko_rate_limit_per_minute,
            "finnhub": settings.finnhub_rate_limit_per_minute,
            "frankfurter": settings.frankfurter_rate_limit_per_minute,
        }.get(provider, 10)
        _buckets[provider] = TokenBucket(per_minute)
    return _buckets[provider]


def reset_buckets() -> None:
    """Test-only."""
    for bucket in _buckets.values():
        bucket.reset()


def get_json(
    provider: str,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float | None = None,
) -> dict | list:
    if not bucket_for(provider).take():
        market_rate_limited_total.labels(provider=provider).inc()
        raise MarketRateLimited(f"{provider}: local request budget exhausted, serving cache")

    merged_headers = {"User-Agent": settings.market_user_agent, "Accept": "application/json"}
    if headers:
        merged_headers.update(headers)

    started = time.monotonic()
    outcome = "error"
    try:
        with httpx.Client(timeout=timeout or settings.market_http_timeout_seconds, follow_redirects=True) as client:
            response = client.get(url, params=params, headers=merged_headers)
    except httpx.TimeoutException as exc:
        raise MarketUnavailable(f"{provider}: timeout") from exc
    except httpx.HTTPError as exc:
        raise MarketUnavailable(f"{provider}: network error ({exc.__class__.__name__})") from exc
    finally:
        market_request_latency_seconds.labels(provider=provider).observe(time.monotonic() - started)

    status = response.status_code
    if status == 429:
        outcome = "rate_limited"
        market_requests_total.labels(provider=provider, outcome=outcome).inc()
        log_event(logger, 30, "provider rate limited us", provider=provider, status=status)
        raise MarketRateLimited(f"{provider}: HTTP 429", remote=True)
    if status == 404:
        outcome = "not_found"
        market_requests_total.labels(provider=provider, outcome=outcome).inc()
        raise MarketNotFound(f"{provider}: HTTP 404")
    if status in (401, 403):
        outcome = "forbidden"
        market_requests_total.labels(provider=provider, outcome=outcome).inc()
        raise MarketNotSupported(f"{provider}: HTTP {status} (credential missing/invalid or plan restriction)")
    if status >= 400:
        market_requests_total.labels(provider=provider, outcome="error").inc()
        raise MarketUnavailable(f"{provider}: HTTP {status}")

    try:
        payload = response.json()
    except ValueError as exc:
        market_requests_total.labels(provider=provider, outcome="parse_error").inc()
        raise MarketUnavailable(f"{provider}: invalid JSON") from exc

    market_requests_total.labels(provider=provider, outcome="ok").inc()
    return payload


__all__ = ["get_json", "bucket_for", "reset_buckets", "MarketDataError"]
