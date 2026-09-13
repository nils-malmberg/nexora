"""Bounded retry with backoff for adapter calls.

Only transient failures (timeout, HTTP 5xx/connection errors, rate limits)
are retried; `AdapterParseError` / `AdapterMisconfigured` are not transient
and propagate immediately so the pipeline does not waste a fetch budget
retrying a malformed feed or a missing credential.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from app.config import settings
from app.news.adapters.base import AdapterHTTPError, AdapterRateLimited, AdapterTimeout

T = TypeVar("T")


class RetriesExhausted(Exception):
    def __init__(self, last_error: Exception):
        super().__init__(str(last_error))
        self.last_error = last_error


def call_with_retries(
    fn: Callable[[], T],
    *,
    max_retries: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    max_retries = settings.max_retries if max_retries is None else max_retries
    attempt = 0
    while True:
        try:
            return fn()
        except AdapterRateLimited as exc:
            attempt += 1
            if attempt > max_retries:
                raise RetriesExhausted(exc) from exc
            delay = (
                exc.retry_after_seconds
                if exc.retry_after_seconds is not None
                else settings.retry_backoff_base_seconds * (2 ** (attempt - 1))
            )
            sleep(delay)
        except (AdapterTimeout, AdapterHTTPError) as exc:
            attempt += 1
            if attempt > max_retries:
                raise RetriesExhausted(exc) from exc
            sleep(settings.retry_backoff_base_seconds * (2 ** (attempt - 1)))
