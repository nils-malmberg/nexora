"""Password hashing, session tokens, CSRF, and a minimal auth rate limiter.

Sessions are opaque, server-revocable tokens (not self-contained JWTs): only
a session's SHA-256 hash is ever persisted, so a stolen DB row cannot be
replayed as a cookie, and a single row deletion revokes it immediately in an
incident — see specs/SECURITY.md.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


class RateLimiter:
    """In-memory sliding-window limiter, keyed by an arbitrary string (e.g.
    "login:<email>" or "login:<ip>"). Single-instance limitation, documented
    in README — the same "no dedicated cache" trade-off the News & Events
    module made deliberately for V1."""

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            attempts = [t for t in self._attempts[key] if now - t < self._window_seconds]
            self._attempts[key] = attempts
            return len(attempts) < self._max_attempts

    def record(self, key: str) -> None:
        with self._lock:
            self._attempts[key].append(time.monotonic())

    def clear(self) -> None:
        """Test-only reset: the limiter is a module-level singleton (see
        app/api/routers/auth.py), so its state otherwise leaks across tests
        that all appear to come from the same client IP."""
        with self._lock:
            self._attempts.clear()
