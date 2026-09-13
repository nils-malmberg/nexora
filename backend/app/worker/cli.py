"""Manual ingestion trigger, for local development and operational runbooks
(see docs/OPERATIONS.md): `python -m app.worker.cli sync <provider-name>` or
`python -m app.worker.cli sync-all`."""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Provider
from app.news.pipeline.ingest import run_provider
from app.observability.logging import configure_logging


def sync_one(provider_name: str) -> int:
    db = SessionLocal()
    try:
        provider = db.scalar(select(Provider).where(Provider.name == provider_name))
        if provider is None:
            print(f"no provider named '{provider_name}'", file=sys.stderr)
            return 1
        run = run_provider(db, provider)
        print(f"provider={provider.name} status={run.status} counts={run.counts}")
        return 0 if run.status in ("success", "partial") else 1
    finally:
        db.close()


def sync_all() -> int:
    db = SessionLocal()
    try:
        providers = db.scalars(select(Provider).where(Provider.enabled.is_(True))).all()
        exit_code = 0
        for provider in providers:
            run = run_provider(db, provider)
            print(f"provider={provider.name} status={run.status} counts={run.counts}")
            if run.status == "failed":
                exit_code = 1
        return exit_code
    finally:
        db.close()


def main() -> None:
    configure_logging(settings.log_level)
    if len(sys.argv) < 2 or sys.argv[1] not in ("sync", "sync-all"):
        print("usage: python -m app.worker.cli sync <provider-name> | sync-all", file=sys.stderr)
        sys.exit(2)

    if sys.argv[1] == "sync-all":
        sys.exit(sync_all())
    else:
        if len(sys.argv) != 3:
            print("usage: python -m app.worker.cli sync <provider-name>", file=sys.stderr)
            sys.exit(2)
        sys.exit(sync_one(sys.argv[2]))


if __name__ == "__main__":
    main()
