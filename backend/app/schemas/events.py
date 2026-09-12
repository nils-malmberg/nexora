from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EventSourceOut(BaseModel):
    url: str
    citation: str | None
    retrieved_at: datetime
    is_primary: bool

    model_config = {"from_attributes": True}


class EventStatusHistoryOut(BaseModel):
    old_status: str | None
    new_status: str
    changed_at: datetime
    source_url: str | None

    model_config = {"from_attributes": True}


class EventOut(BaseModel):
    id: str
    asset_id: str
    type: str
    starts_at: datetime | None
    period_label: str | None
    timezone: str
    status: str
    amount: float | None
    currency: str | None
    last_verified_at: datetime
    stale: bool
    sources: list[EventSourceOut]
    status_history: list[EventStatusHistoryOut]

    model_config = {"from_attributes": True}
