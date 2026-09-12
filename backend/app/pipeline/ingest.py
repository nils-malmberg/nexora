"""Ingestion orchestrator: fetch -> normalize -> resolve asset -> dedupe ->
score -> summarize -> persist, with retries, a per-provider circuit
breaker, and idempotent upserts. One `IngestionRun` row is written per
provider per invocation, aggregating counts across all of that provider's
feeds (matches the minimal data model in specs/NEWS_AND_EVENTS.md).

A failure on one feed, or one malformed record, never aborts the whole run:
partial failures are isolated (per-record SAVEPOINT) and reflected in the
run's `counts` and `status` rather than losing already-good data - this is
what "mode dégradé" means for this module (see "Architecture et
résilience").
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.adapters.base import (
    AdapterError,
    AdapterMisconfigured,
    AdapterParseError,
    NormalizedEvent,
    NormalizedNewsItem,
)
from app.adapters.registry import build_adapter
from app.config import settings
from app.models import (
    Event,
    EventSource,
    EventStatusHistory,
    IngestionRun,
    NewsItem,
    NewsItemAsset,
    NewsItemRelation,
    Provider,
    new_id,
)
from app.observability.logging import get_logger, log_event
from app.observability.metrics import (
    ingestion_latency_seconds,
    ingestion_runs_total,
    items_processed_total,
    parsing_errors_total,
    provider_auto_disabled_total,
    provider_up,
)
from app.pipeline.assets import resolve_asset
from app.pipeline.cache import snapshot_freshness_label
from app.pipeline.dedupe import find_exact_news_duplicate, find_matching_event, find_near_duplicate_news
from app.pipeline.retry import RetriesExhausted, call_with_retries
from app.pipeline.scoring import ScoreInput, compute_relevance
from app.pipeline.summarize import summarize

logger = get_logger(__name__)


def _circuit_allows(provider: Provider, now: datetime) -> bool:
    if provider.circuit_state == "open":
        reset_due = (
            provider.last_attempt_at
            and (now - provider.last_attempt_at).total_seconds() >= settings.circuit_breaker_reset_seconds
        )
        if reset_due:
            provider.circuit_state = "half_open"
            return True
        return False
    return True


def _record_success(provider: Provider, now: datetime) -> None:
    provider.consecutive_failures = 0
    provider.circuit_state = "closed"
    provider.last_success_at = now
    provider.last_attempt_at = now


def _record_failure(provider: Provider, now: datetime) -> None:
    provider.consecutive_failures += 1
    provider.last_attempt_at = now
    threshold_reached = provider.consecutive_failures >= settings.circuit_breaker_failure_threshold
    if threshold_reached or provider.circuit_state == "half_open":
        provider.circuit_state = "open"

    if provider.consecutive_failures >= settings.auto_disable_after_failures:
        provider.enabled = False
        provider_auto_disabled_total.labels(provider_id=provider.id).inc()
        log_event(
            logger,
            logging.ERROR,
            "provider auto-disabled after too many consecutive failures - requires manual re-enable",
            provider_id=provider.id,
            consecutive_failures=provider.consecutive_failures,
        )


def _upsert_news_item(db: Session, run_id: str, normalized: NormalizedNewsItem, counts: dict) -> None:
    resolution = resolve_asset(db, normalized.asset_hint, normalized.asset_match_confidence)
    if resolution.asset_id is None:
        counts["unmatched_asset"] += 1

    existing = find_exact_news_duplicate(db, normalized.content_hash)
    if existing is not None:
        changed = (
            existing.title != normalized.title
            or existing.excerpt != normalized.excerpt
            or existing.category != normalized.category
            or existing.event_at != normalized.event_at
        )
        existing.title = normalized.title
        existing.excerpt = normalized.excerpt
        existing.category = normalized.category
        existing.kind = normalized.kind
        existing.event_at = normalized.event_at
        existing.citation = normalized.citation
        existing.confidence = normalized.confidence
        existing.language = normalized.language
        if changed:
            existing.verification_status = "corrected"
        item = existing
        counts["updated"] += 1
    else:
        near = find_near_duplicate_news(
            db,
            asset_id=resolution.asset_id,
            provider_id=normalized.provider_id,
            title=normalized.title,
            publication_at=normalized.publication_at,
            exclude_content_hash=normalized.content_hash,
        )
        item = NewsItem(
            id=new_id(),
            provider_id=normalized.provider_id,
            kind=normalized.kind,
            category=normalized.category,
            title=normalized.title,
            excerpt=normalized.excerpt,
            publication_at=normalized.publication_at,
            event_at=normalized.event_at,
            timezone=normalized.timezone,
            url=normalized.url,
            citation=normalized.citation,
            provenance=normalized.provenance,
            confidence=normalized.confidence,
            language=normalized.language,
            content_hash=normalized.content_hash,
            raw_meta=normalized.raw_meta,
            freshness_at_collection=snapshot_freshness_label(
                is_estimated=normalized.kind == "prediction", has_known_date=True
            ),
        )
        db.add(item)
        db.flush()
        if near is not None:
            db.add(
                NewsItemRelation(
                    news_item_id=item.id,
                    related_news_item_id=near.news_item.id,
                    relation_type=near.relation_type,
                )
            )
            counts[f"relation_{near.relation_type}"] += 1
        counts["inserted"] += 1

    if resolution.asset_id is not None:
        link_exists = any(link.asset_id == resolution.asset_id for link in item.asset_links)
        if not link_exists:
            db.add(
                NewsItemAsset(
                    news_item_id=item.id,
                    asset_id=resolution.asset_id,
                    match_confidence=resolution.confidence,
                    match_method=resolution.method,
                )
            )

    db.flush()
    corroboration_count = sum(
        1
        for rel in db.query(NewsItemRelation).filter(NewsItemRelation.news_item_id == item.id).all()
        if rel.relation_type == "corroborates"
    )
    item.summary = summarize(item.title, item.excerpt)
    score, breakdown = compute_relevance(
        ScoreInput(
            asset_match_confidence=resolution.confidence if resolution.asset_id else 0.0,
            category=item.category,
            has_event_at=item.event_at is not None,
            provenance_confidence=item.confidence,
            corroboration_count=corroboration_count,
            reference_at=item.event_at or item.publication_at,
            now=datetime.now(UTC),
        )
    )
    item.relevance_score = score
    item.relevance_breakdown = breakdown


def _upsert_event(db: Session, normalized: NormalizedEvent, counts: dict) -> None:
    resolution = resolve_asset(db, normalized.asset_hint, normalized.asset_match_confidence)
    if resolution.asset_id is None:
        counts["event_unmatched_asset"] += 1
        return

    existing = find_matching_event(
        db,
        asset_id=resolution.asset_id,
        type_=normalized.type,
        starts_at=normalized.starts_at,
        period_label=normalized.period_label,
    )
    now = datetime.now(UTC)

    if existing is None:
        event = Event(
            id=new_id(),
            asset_id=resolution.asset_id,
            provider_id=normalized.provider_id,
            type=normalized.type,
            starts_at=normalized.starts_at,
            period_label=normalized.period_label,
            timezone=normalized.timezone,
            status=normalized.status,
            amount=normalized.amount,
            currency=normalized.currency,
            last_verified_at=now,
            content_hash=normalized.content_hash,
        )
        db.add(event)
        db.flush()
        db.add(EventSource(event_id=event.id, url=normalized.source_url, citation=normalized.citation))
        db.add(
            EventStatusHistory(
                event_id=event.id, old_status=None, new_status=normalized.status, source_url=normalized.source_url
            )
        )
        counts["event_inserted"] += 1
        return

    existing_urls = {s.url for s in existing.sources}
    if normalized.source_url not in existing_urls:
        db.add(EventSource(event_id=existing.id, url=normalized.source_url, citation=normalized.citation))

    if normalized.status != existing.status:
        db.add(
            EventStatusHistory(
                event_id=existing.id,
                old_status=existing.status,
                new_status=normalized.status,
                source_url=normalized.source_url,
            )
        )
        existing.status = normalized.status

    if existing.amount is None and normalized.amount is not None:
        existing.amount = normalized.amount
        existing.currency = normalized.currency

    existing.last_verified_at = now
    counts["event_updated"] += 1


def run_provider(db: Session, provider: Provider) -> IngestionRun:
    now = datetime.now(UTC)
    run = IngestionRun(id=new_id(), provider_id=provider.id, started_at=now, status="running", counts={})
    db.add(run)
    db.flush()

    if not provider.enabled:
        run.status = "failed"
        run.error_code = "provider_disabled"
        run.ended_at = datetime.now(UTC)
        db.commit()
        return run

    if not _circuit_allows(provider, now):
        run.status = "failed"
        run.error_code = "circuit_open"
        run.ended_at = datetime.now(UTC)
        log_event(
            logger,
            logging.WARNING,
            "ingestion skipped: circuit open",
            provider_id=provider.id,
            ingestion_run_id=run.id,
        )
        db.commit()
        return run

    counts: dict = defaultdict(int)
    started = time.monotonic()
    adapter = build_adapter(provider.type, provider.id, provider.config)
    any_feed_failed = False
    any_feed_succeeded = False

    for feed in provider.feeds:
        try:
            fetch_result = call_with_retries(
                lambda f=feed: adapter.fetch(f.url, f.extra_config, provider.last_success_at)
            )
        except (RetriesExhausted, AdapterError) as exc:
            any_feed_failed = True
            log_event(
                logger,
                logging.ERROR,
                "feed fetch failed",
                provider_id=provider.id,
                ingestion_run_id=run.id,
                feed_url=feed.url,
                error=str(exc),
            )
            continue

        any_feed_succeeded = True
        for record in fetch_result.items:
            counts["fetched"] += 1
            try:
                normalized = adapter.normalize(record)
            except (AdapterParseError, AdapterMisconfigured) as exc:
                counts["skipped_parse_errors"] += 1
                parsing_errors_total.labels(provider_id=provider.id).inc()
                log_event(
                    logger,
                    logging.WARNING,
                    "record normalization failed",
                    provider_id=provider.id,
                    ingestion_run_id=run.id,
                    error=str(exc),
                )
                continue

            savepoint = db.begin_nested()
            try:
                if isinstance(normalized, NormalizedNewsItem):
                    _upsert_news_item(db, run.id, normalized, counts)
                else:
                    _upsert_event(db, normalized, counts)
                savepoint.commit()
            except Exception:
                savepoint.rollback()
                counts["record_errors"] += 1
                logger.exception(
                    "unexpected error persisting one record", extra={"fields": {"provider_id": provider.id}}
                )

    latency = time.monotonic() - started
    ingestion_latency_seconds.labels(provider_id=provider.id).observe(latency)

    if not any_feed_succeeded and any_feed_failed:
        run.status = "failed"
        run.error_code = "all_feeds_failed"
        _record_failure(provider, now)
    elif any_feed_failed or counts.get("skipped_parse_errors") or counts.get("record_errors"):
        run.status = "partial"
        _record_success(provider, now)
    else:
        run.status = "success"
        _record_success(provider, now)

    for outcome, count in counts.items():
        items_processed_total.labels(provider_id=provider.id, outcome=outcome).inc(count)
    provider_up.labels(provider_id=provider.id).set(1 if provider.circuit_state == "closed" else 0)
    ingestion_runs_total.labels(provider_id=provider.id, status=run.status).inc()

    run.counts = dict(counts)
    run.ended_at = datetime.now(UTC)
    run.latency_ms = int(latency * 1000)
    db.commit()
    return run


def run_all(db: Session) -> list[IngestionRun]:
    from sqlalchemy import select

    providers = db.scalars(select(Provider).where(Provider.enabled.is_(True))).all()
    return [run_provider(db, provider) for provider in providers]
