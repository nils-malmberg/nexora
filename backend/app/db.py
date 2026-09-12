from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import settings


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """DateTime that always round-trips as UTC-aware, on every backend.

    Postgres' timestamptz already does this; SQLite silently drops tzinfo on
    read-back even with `DateTime(timezone=True)` (verified empirically), and
    the test suite runs against SQLite (see specs/TESTING.md - no external
    service by default). Without this, every comparison between a
    freshly-computed aware `datetime.now(timezone.utc)` and a value read back
    from the DB would raise `TypeError` in tests only, while working in
    production - the worst kind of environment-specific bug.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def _make_engine():
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, connect_args=connect_args, future=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
