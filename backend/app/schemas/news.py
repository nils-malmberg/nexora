from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RelatedItemRef(BaseModel):
    news_item_id: str
    title: str
    provenance: str


class NewsItemOut(BaseModel):
    id: str
    instrument_ids: list[str]
    provider_id: str
    provider_name: str
    kind: str
    category: str
    title: str
    excerpt: str | None
    summary: str | None
    url: str
    citation: str | None
    provenance: str
    publication_at: datetime
    event_at: datetime | None
    timezone: str
    confidence: float
    relevance_score: float
    relevance_breakdown: dict
    language: str | None
    collected_at: datetime
    updated_at: datetime
    freshness_at_collection: str
    stale: bool
    verification_status: str
    duplicate_of: list[RelatedItemRef]
    corroborated_by: list[RelatedItemRef]

    model_config = {"from_attributes": True}
