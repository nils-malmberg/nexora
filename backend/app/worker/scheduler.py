"""Periodic ingestion runner.

Runs as its own process (see docker-compose.yml), separate from the API, so
a slow or failing provider never blocks a dashboard request - the
"Workers" component in specs/ARCHITECTURE.md. Deliberately a single
APScheduler process rather than a Celery/Redis stack: at V1 volumes this is
enough infrastructure to be reliable without adding a queue broker to
operate and secure.
"""

from __future__ import annotations

import random

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Provider
from app.observability.logging import configure_logging, get_logger, log_event
from app.pipeline.ingest import run_provider

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


def main() -> None:
    configure_logging(settings.log_level)
    scheduler = BlockingScheduler()
    jitter = random.uniform(0, settings.ingestion_jitter_seconds)
    scheduler.add_job(
        run_all_enabled_providers,
        "interval",
        seconds=settings.ingestion_interval_seconds,
        next_run_time=None,
        jitter=int(jitter),
        id="ingest_all_providers",
    )
    log_event(logger, 20, "worker starting", interval_seconds=settings.ingestion_interval_seconds)
    scheduler.start()


if __name__ == "__main__":
    main()
