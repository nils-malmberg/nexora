"""Historical timeline: news and events for one asset, merged and sorted by
event date then publication date (specs/NEWS_AND_EVENTS.md). Entries without
a known event date are positioned by publication date instead, and flagged
via `date_basis` rather than having a date silently invented for them."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.common import ALLOWED_CATEGORIES
from app.api.bucketing import GRANULARITIES, bucket_label
from app.api.deps import get_db
from app.api.serializers import event_to_out, news_item_to_out
from app.models import Asset, Event, NewsItem, NewsItemAsset
from app.schemas.timeline import TimelineEntryOut

router = APIRouter(prefix="/api/v1/assets", tags=["timeline"])

DEFAULT_TIMELINE_LIMIT = 200


@router.get("/{asset_id}/timeline", response_model=list[TimelineEntryOut])
def get_asset_timeline(
    asset_id: str,
    granularity: str = Query(default="month"),
    category: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=DEFAULT_TIMELINE_LIMIT, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[TimelineEntryOut]:
    if db.get(Asset, asset_id) is None:
        raise HTTPException(status_code=404, detail="asset not found")
    if granularity not in GRANULARITIES:
        raise HTTPException(status_code=400, detail=f"unknown granularity '{granularity}'")
    if category is not None and category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"unknown category '{category}'")

    news_query = (
        select(NewsItem)
        .join(NewsItemAsset, NewsItemAsset.news_item_id == NewsItem.id)
        .where(NewsItemAsset.asset_id == asset_id)
    )
    events_query = select(Event).where(Event.asset_id == asset_id)
    if category:
        news_query = news_query.where(NewsItem.category == category)
    if since:
        news_query = news_query.where(NewsItem.publication_at >= since)
        events_query = events_query.where(Event.starts_at >= since)
    if until:
        news_query = news_query.where(NewsItem.publication_at <= until)
        events_query = events_query.where(Event.starts_at <= until)

    entries: list[TimelineEntryOut] = []

    for item in db.scalars(news_query).all():
        effective_at = item.event_at or item.publication_at
        basis = "event_date" if item.event_at else "publication_date"
        entries.append(
            TimelineEntryOut(
                entry_type="news",
                effective_at=effective_at,
                date_basis=basis,
                bucket=bucket_label(effective_at, granularity),
                news_item=news_item_to_out(item, db),
            )
        )

    for event in db.scalars(events_query).all():
        effective_at = event.starts_at
        basis = "event_date"
        if effective_at is None and event.period_label:
            try:
                parsed = date.fromisoformat(event.period_label)
                effective_at = datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)
                basis = "period"
            except ValueError:
                basis = "unknown"
        elif effective_at is None:
            basis = "unknown"
        entries.append(
            TimelineEntryOut(
                entry_type="event",
                effective_at=effective_at,
                date_basis=basis,
                bucket=bucket_label(effective_at, granularity),
                event=event_to_out(event),
            )
        )

    entries.sort(key=lambda e: e.effective_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    return entries[:limit]
