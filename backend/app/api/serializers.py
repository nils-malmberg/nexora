"""ORM -> API schema mapping shared by the news, timeline, and events
routers, so `stale`, provider name resolution, and duplicate/corroboration
links are computed exactly the same way everywhere they are shown."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Event, NewsItem, NewsItemRelation, Provider
from app.pipeline.cache import is_stale
from app.schemas.events import EventOut
from app.schemas.news import NewsItemOut, RelatedItemRef


def news_item_to_out(item: NewsItem, db: Session, *, now: datetime | None = None) -> NewsItemOut:
    now = now or datetime.now(UTC)
    provider = db.get(Provider, item.provider_id)
    relations = db.scalars(
        select(NewsItemRelation).where(
            (NewsItemRelation.news_item_id == item.id) | (NewsItemRelation.related_news_item_id == item.id)
        )
    ).all()

    duplicate_of: list[RelatedItemRef] = []
    corroborated_by: list[RelatedItemRef] = []
    for rel in relations:
        is_owner = rel.news_item_id == item.id
        other_id = rel.related_news_item_id if is_owner else rel.news_item_id
        other = db.get(NewsItem, other_id)
        if other is None:
            continue
        ref = RelatedItemRef(news_item_id=other.id, title=other.title, provenance=other.provenance)
        if rel.relation_type == "duplicate_of" and is_owner:
            duplicate_of.append(ref)
        elif rel.relation_type == "corroborates":
            corroborated_by.append(ref)

    return NewsItemOut(
        id=item.id,
        asset_ids=[link.asset_id for link in item.asset_links],
        provider_id=item.provider_id,
        provider_name=provider.name if provider else item.provider_id,
        kind=item.kind,
        category=item.category,
        title=item.title,
        excerpt=item.excerpt,
        summary=item.summary,
        url=item.url,
        citation=item.citation,
        provenance=item.provenance,
        publication_at=item.publication_at,
        event_at=item.event_at,
        timezone=item.timezone,
        confidence=item.confidence,
        relevance_score=item.relevance_score,
        relevance_breakdown=item.relevance_breakdown,
        language=item.language,
        collected_at=item.collected_at,
        updated_at=item.updated_at,
        freshness_at_collection=item.freshness_at_collection,
        stale=is_stale(item.updated_at, settings.news_freshness_minutes, now),
        verification_status=item.verification_status,
        duplicate_of=duplicate_of,
        corroborated_by=corroborated_by,
    )


def event_to_out(event: Event, *, now: datetime | None = None, display_tz=None) -> EventOut:
    now = now or datetime.now(UTC)
    starts_at = event.starts_at
    if starts_at is not None and display_tz is not None:
        starts_at = starts_at.astimezone(display_tz)
    return EventOut.model_validate(
        {
            "id": event.id,
            "asset_id": event.asset_id,
            "type": event.type,
            "starts_at": starts_at,
            "period_label": event.period_label,
            "timezone": str(display_tz) if display_tz is not None else event.timezone,
            "status": event.status,
            "amount": float(event.amount) if event.amount is not None else None,
            "currency": event.currency,
            "last_verified_at": event.last_verified_at,
            "stale": is_stale(event.last_verified_at, settings.event_freshness_minutes, now),
            "sources": event.sources,
            "status_history": event.status_history,
        }
    )


def compute_list_etag(ids_and_versions: list[tuple[str, datetime]]) -> str:
    basis = "|".join(f"{id_}:{version.isoformat()}" for id_, version in ids_and_versions)
    return 'W/"' + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32] + '"'
