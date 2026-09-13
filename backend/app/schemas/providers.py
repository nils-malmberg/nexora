from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ProviderStatusOut(BaseModel):
    """A news/events source (RSS, JSON API, calendar)."""

    id: str
    name: str
    type: str
    enabled: bool
    circuit_state: str
    consecutive_failures: int
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    healthy: bool
    license_note: str | None

    model_config = {"from_attributes": True}


class IngestionRunOut(BaseModel):
    id: str
    provider_id: str
    started_at: datetime
    ended_at: datetime | None
    status: str
    counts: dict
    error_code: str | None
    latency_ms: int | None

    model_config = {"from_attributes": True}


class MarketProviderStateOut(BaseModel):
    """A market-data / FX source's runtime state (never its credential)."""

    name: str
    enabled: bool
    env_var: str | None
    license_note: str | None
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    consecutive_failures: int
    circuit_state: str
    disabled_reason: str | None

    model_config = {"from_attributes": True}


class MarketProviderPublicOut(BaseModel):
    name: str
    role: str  # equity | crypto | fx
    enabled: bool
    healthy: bool
    circuit_state: str
    last_success_at: datetime | None
    attribution: str | None
    license_note: str | None
    capabilities: dict


class AutoNewsOut(BaseModel):
    provider: str
    configured: bool
    env_var: str
    detail: str


class ProvidersOverviewOut(BaseModel):
    market: list[MarketProviderPublicOut]
    news: list[ProviderStatusOut]
    auto_news: AutoNewsOut
    prediction_enabled: bool
    quote_freshness_minutes: int
