"""Periodic worker: news/events ingestion and market-data refresh.

Runs as its own process (see docker-compose.yml), separate from the API, so
a slow or failing provider never blocks a dashboard request — the "Workers"
component in specs/ARCHITECTURE.md. Deliberately a single APScheduler
process rather than a Celery/Redis stack: at V1 volumes this is enough
infrastructure to be reliable without a queue broker to operate and secure.

Cadence is the only place where outbound request volume is decided:
- news providers every `ingestion_interval_seconds` (default 15 min);
- market quotes/history for *tracked* instruments (held or watched) every
  `market_refresh_interval_seconds` (default 15 min), sequentially, under the
  per-provider token buckets — an idle dashboard costs a handful of requests
  per quarter hour, never a burst.
"""

from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from prometheus_client import start_http_server
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.market import service as market_service
from app.models import Provider
from app.news.pipeline.ingest import run_provider
from app.observability.logging import configure_logging, get_logger, log_event

logger = get_logger(__name__)


def run_all_enabled_providers() -> None:
    db = SessionLocal()
    try:
        providers = db.scalars(select(Provider).where(Provider.enabled.is_(True))).all()
        for provider in providers:
            try:
                run = run_provider(db, provider)
                log_event(
                    logger,
                    20,
                    "ingestion run finished",
                    provider_id=provider.id,
                    status=run.status,
                    ingestion_run_id=run.id,
                )
            except Exception:
                logger.exception("unhandled error running provider", extra={"fields": {"provider_id": provider.id}})
    finally:
        db.close()


def refresh_market_data() -> None:
    db = SessionLocal()
    try:
        summary = market_service.refresh_tracked(db)
        log_event(logger, 20, "market refresh finished", **summary)
    except Exception:
        logger.exception("unhandled error refreshing market data")
    finally:
        db.close()


def main() -> None:
    configure_logging(settings.log_level)
    start_http_server(settings.worker_metrics_port)
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_all_enabled_providers,
        "interval",
        seconds=settings.ingestion_interval_seconds,
        jitter=settings.ingestion_jitter_seconds,
        id="ingest_all_providers",
    )
    scheduler.add_job(
        refresh_market_data,
        "interval",
        seconds=settings.market_refresh_interval_seconds,
        jitter=settings.ingestion_jitter_seconds,
        id="refresh_market_data",
    )
    log_event(
        logger,
        20,
        "worker starting",
        ingestion_interval_seconds=settings.ingestion_interval_seconds,
        market_refresh_interval_seconds=settings.market_refresh_interval_seconds,
    )
    run_all_enabled_providers()  # data available right after startup, not after a full interval
    refresh_market_data()
    scheduler.start()


if __name__ == "__main__":
    main()
