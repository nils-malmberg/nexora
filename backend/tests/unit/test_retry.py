import pytest

from app.adapters.base import AdapterParseError, AdapterRateLimited, AdapterTimeout
from app.pipeline.retry import RetriesExhausted, call_with_retries


def test_succeeds_without_retry():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert call_with_retries(fn, sleep=lambda s: None) == "ok"
    assert len(calls) == 1


def test_retries_transient_errors_then_succeeds():
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise AdapterTimeout("timeout")
        return "ok"

    sleeps = []
    result = call_with_retries(fn, max_retries=5, sleep=sleeps.append)
    assert result == "ok"
    assert attempts["n"] == 3
    assert len(sleeps) == 2
    assert sleeps == sorted(sleeps)  # exponential backoff: non-decreasing


def test_raises_retries_exhausted_after_max_attempts():
    def fn():
        raise AdapterTimeout("still down")

    with pytest.raises(RetriesExhausted):
        call_with_retries(fn, max_retries=2, sleep=lambda s: None)


def test_rate_limit_honors_retry_after():
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise AdapterRateLimited("slow down", retry_after_seconds=42.0)
        return "ok"

    sleeps = []
    assert call_with_retries(fn, max_retries=3, sleep=sleeps.append) == "ok"
    assert sleeps == [42.0]


def test_parse_error_is_not_retried():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise AdapterParseError("malformed")

    with pytest.raises(AdapterParseError):
        call_with_retries(fn, max_retries=5, sleep=lambda s: None)
    assert calls["n"] == 1
