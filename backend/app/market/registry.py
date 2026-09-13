"""Provider selection and shared circuit-breaker state.

Which adapter serves which asset family is configuration
(`NEXORA_MARKET_EQUITY_PROVIDER`, `..._CRYPTO_PROVIDER`, `..._FX_PROVIDER`),
so swapping Yahoo for Finnhub — or disabling live data entirely — is an env
change, not a code change. Breaker state lives in the `market_providers`
table so the api and worker processes see the same picture, and a provider
that keeps failing disables itself after N consecutive failures instead of
being probed forever (the lesson of the SEC EDGAR incident, see
specs/DATA_SOURCES.md).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.market.base import FxProvider, MarketDataProvider
from app.market.coingecko import CoinGeckoProvider
from app.market.finnhub import FinnhubProvider
from app.market.fixture import FixtureFxProvider, FixtureProvider, NullFxProvider, NullProvider
from app.market.frankfurter import FrankfurterProvider
from app.market.yahoo import YahooProvider
from app.models import MarketProvider
from app.observability.logging import get_logger, log_event
from app.observability.metrics import market_provider_up

logger = get_logger(__name__)

_instances: dict[str, MarketDataProvider | FxProvider] = {}
_overrides: dict[str, MarketDataProvider | FxProvider] = {}

_ENV_VARS = {"finnhub": settings.finnhub_api_key_env_var, "coingecko": settings.coingecko_api_key_env_var}


def set_override(name: str, provider: MarketDataProvider | FxProvider | None) -> None:
    """Test hook: force a provider instance (or clear with None)."""
    if provider is None:
        _overrides.pop(name, None)
    else:
        _overrides[name] = provider


def build_provider(name: str) -> MarketDataProvider:
    if name in _overrides:
        return _overrides[name]  # type: ignore[return-value]
    if name not in _instances:
        if name == "yahoo":
            _instances[name] = YahooProvider()
        elif name == "coingecko":
            _instances[name] = CoinGeckoProvider()
        elif name == "finnhub":
            _instances[name] = FinnhubProvider()
        elif name == "fixture":
            _instances[name] = FixtureProvider(Path(settings.market_fixture_path))
        else:
            _instances[name] = NullProvider()
    return _instances[name]  # type: ignore[return-value]


def fx_provider() -> FxProvider:
    name = settings.market_fx_provider
    if name in _overrides:
        return _overrides[name]  # type: ignore[return-value]
    key = f"fx:{name}"
    if key not in _instances:
        if name == "frankfurter":
            _instances[key] = FrankfurterProvider()
        elif name == "fixture":
            _instances[key] = FixtureFxProvider({"USD": {"EUR": "0.92", "GBP": "0.79"}, "EUR": {"USD": "1.087"}})
        else:
            _instances[key] = NullFxProvider()
    return _instances[key]  # type: ignore[return-value]


def provider_name_for(asset_class: str) -> str:
    if asset_class == "crypto":
        return settings.market_crypto_provider
    if asset_class == "actif_prive":
        return "null"
    return settings.market_equity_provider


def provider_for(asset_class: str) -> MarketDataProvider:
    return build_provider(provider_name_for(asset_class))


def configured_provider_names() -> list[str]:
    names = []
    for name in (settings.market_equity_provider, settings.market_crypto_provider):
        if name != "null" and name not in names:
            names.append(name)
    return names


# --- persisted breaker state ------------------------------------------------


def get_state(db: Session, name: str) -> MarketProvider:
    state = db.get(MarketProvider, name)
    if state is None:
        state = MarketProvider(name=name, enabled=True, env_var=_ENV_VARS.get(name))
        provider = build_provider(name) if name != settings.market_fx_provider else None
        if provider is not None:
            state.license_note = provider.capabilities.license_note[:500]
        db.add(state)
        db.flush()
    return state


def circuit_allows(db: Session, name: str, now: datetime | None = None) -> bool:
    state = get_state(db, name)
    if not state.enabled:
        return False
    now = now or datetime.now(UTC)
    if state.circuit_state == "open":
        if (
            state.last_attempt_at is not None
            and (now - state.last_attempt_at).total_seconds() >= settings.market_circuit_reset_seconds
        ):
            state.circuit_state = "half_open"
            return True
        return False
    return True


def record_success(db: Session, name: str) -> None:
    state = get_state(db, name)
    now = datetime.now(UTC)
    state.consecutive_failures = 0
    state.circuit_state = "closed"
    state.last_attempt_at = now
    state.last_success_at = now
    state.last_error = None
    market_provider_up.labels(provider=name).set(1)


def record_failure(db: Session, name: str, error: str, *, open_circuit: bool = True) -> None:
    state = get_state(db, name)
    now = datetime.now(UTC)
    state.consecutive_failures += 1
    state.last_attempt_at = now
    state.last_error = error[:300]
    if open_circuit and (state.consecutive_failures >= 3 or state.circuit_state == "half_open"):
        state.circuit_state = "open"
        market_provider_up.labels(provider=name).set(0)
    if state.consecutive_failures >= settings.market_auto_disable_after_failures:
        state.enabled = False
        state.disabled_reason = f"auto-disabled after {state.consecutive_failures} consecutive failures"
        log_event(
            logger,
            logging.ERROR,
            "market provider auto-disabled - requires manual re-enable",
            provider=name,
            consecutive_failures=state.consecutive_failures,
        )
