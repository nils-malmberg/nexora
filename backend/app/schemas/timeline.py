from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.events import EventOut
from app.schemas.news import NewsItemOut


class TimelineEntryOut(BaseModel):
    entry_type: str  # news | event
    effective_at: datetime | None
    date_basis: str  # event_date | publication_date | period | unknown
    bucket: str
    news_item: NewsItemOut | None = None
    event: EventOut | None = None
