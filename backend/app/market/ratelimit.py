"""Per-provider token buckets — the local half of "pas de polling agressif"
(specs/DATA_SOURCES.md). Every outbound market request must first `take()`
a token; when the bucket is empty the caller serves cache instead of
waiting, so a burst of page views can never turn into a burst of requests
against a provider (which is how an IP gets banned — see the SEC EDGAR
incident in specs/DATA_SOURCES.md).

Budgets are per process (api and worker each have their own), sized so that
even both together stay well under each provider's published limit.
"""

from __future__ import annotations

import threading
import time


class TokenBucket:
    def __init__(self, per_minute: int, burst: int | None = None):
        self._rate = max(per_minute, 1) / 60.0
        self._capacity = float(burst if burst is not None else max(1, per_minute // 2))
        self._tokens = self._capacity
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        self._tokens = min(self._capacity, self._tokens + (now - self._updated) * self._rate)
        self._updated = now

    def take(self) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    def available(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens

    def reset(self) -> None:
        with self._lock:
            self._tokens = self._capacity
            self._updated = time.monotonic()


class TTLCache:
    """Tiny thread-safe in-memory cache with per-entry TTL, used to
    short-circuit identical search queries / history fetches within a
    process. Persistent caching lives in the database (PricePoint, OhlcBar,
    FxRate); this only absorbs immediate repeats."""

    def __init__(self, ttl_seconds: float, max_entries: int = 512):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._data: dict = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._data[key]
                return None
            return value

    def set(self, key, value) -> None:
        with self._lock:
            if len(self._data) >= self._max:
                oldest = min(self._data.items(), key=lambda kv: kv[1][0])[0]
                del self._data[oldest]
            self._data[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
