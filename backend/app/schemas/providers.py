from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ProviderStatusOut(BaseModel):
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
