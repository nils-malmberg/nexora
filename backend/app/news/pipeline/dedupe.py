"""Deduplication.

Three signals from specs/NEWS_AND_EVENTS.md are used, from strongest to
weakest:

1. Exact `content_hash` match (same provider, same canonical URL, same
   title, same event date) -> the *same* record re-fetched or corrected:
   upsert in place, never insert a second row (this is what makes repeated
   ingestion idempotent).
2. High title similarity within the same asset and a bounded time window,
   from the *same* provider -> treated as `duplicate_of` (e.g. a feed
   republishing its own item under a new URL).
3. High-but-lower title similarity, *different* provider -> treated as
   `corroborates`: an independent source is never discarded, only linked.

Events use a coarser key (asset + type + scheduled date/period): a second
report of the same calendar entry adds a source and, if the status differs,
an auditable status-history row - it does not create a duplicate event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Event, NewsItem, NewsItemAsset

SAME_PROVIDER_DUPLICATE_RATIO = 0.97


@dataclass
class NearDuplicateMatch:
    news_item: NewsItem
    similarity: float
    relation_type: str  # duplicate_of | corroborates


def find_exact_news_duplicate(db: Session, content_hash: str) -> NewsItem | None:
    return db.scalar(select(NewsItem).where(NewsItem.content_hash == content_hash))


def _title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def find_near_duplicate_news(
    db: Session,
    *,
    instrument_id: str | None,
    provider_id: str,
    title: str,
    publication_at: datetime,
    exclude_content_hash: str,
) -> NearDuplicateMatch | None:
    if instrument_id is None:
        return None

    window = timedelta(hours=settings.dedup_time_window_hours)
    candidates = db.scalars(
        select(NewsItem)
        .join(NewsItemAsset, NewsItemAsset.news_item_id == NewsItem.id)
        .where(
            NewsItemAsset.instrument_id == instrument_id,
            NewsItem.content_hash != exclude_content_hash,
            NewsItem.publication_at >= publication_at - window,
            NewsItem.publication_at <= publication_at + window,
        )
    ).all()

    best: NearDuplicateMatch | None = None
    for candidate in candidates:
        ratio = _title_similarity(title, candidate.title)
        if ratio < settings.dedup_title_similarity_threshold:
            continue
        same_provider_duplicate = candidate.provider_id == provider_id and ratio >= SAME_PROVIDER_DUPLICATE_RATIO
        relation_type = "duplicate_of" if same_provider_duplicate else "corroborates"
        if best is None or ratio > best.similarity:
            best = NearDuplicateMatch(news_item=candidate, similarity=ratio, relation_type=relation_type)
    return best


def find_matching_event(
    db: Session, *, instrument_id: str, type_: str, starts_at: datetime | None, period_label: str | None
) -> Event | None:
    query = select(Event).where(Event.instrument_id == instrument_id, Event.type == type_)
    if starts_at is not None:
        query = query.where(Event.starts_at == starts_at)
    else:
        query = query.where(Event.period_label == period_label)
    return db.scalar(query)
