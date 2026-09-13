"""Non-regression check required by specs/TESTING.md: "Tests de
non-régression démontrant qu'aucun endpoint d'ordre n'existe en V1"."""

from __future__ import annotations

from app.api.main import app

_FORBIDDEN_PATH_MARKERS = ("order", "buy", "sell", "execute", "trade/place", "broker")


def test_no_order_execution_endpoint_exists():
    paths = [route.path for route in app.routes if hasattr(route, "path")]
    offending = [p for p in paths if any(marker in p.lower() for marker in _FORBIDDEN_PATH_MARKERS)]
    assert offending == [], f"found route(s) that look like order execution: {offending}"


def test_only_expected_http_methods_are_registered():
    """A stray PUT/order-shaped verb combination would be an early signal of
    scope creep beyond V1 (read/write portfolio state, never market
    execution)."""
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if methods is None:
            continue
        assert methods.issubset({"GET", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS"})
