from __future__ import annotations

import time

from app.security import RateLimiter, hash_password, hash_token, verify_password


def test_hash_password_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password(hashed, "correct horse battery staple")


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert not verify_password(hashed, "wrong password entirely")


def test_hash_token_is_deterministic_and_unique_per_input():
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("abd")


def test_rate_limiter_blocks_after_threshold():
    limiter = RateLimiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        assert limiter.allow("key")
        limiter.record("key")
    assert not limiter.allow("key")


def test_rate_limiter_is_keyed_independently():
    limiter = RateLimiter(max_attempts=1, window_seconds=60)
    limiter.record("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")


def test_rate_limiter_window_expires(monkeypatch):
    limiter = RateLimiter(max_attempts=1, window_seconds=1)
    limiter.record("key")
    assert not limiter.allow("key")
    time.sleep(1.05)
    assert limiter.allow("key")
