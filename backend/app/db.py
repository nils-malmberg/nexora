from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import settings


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """DateTime that always round-trips as UTC-aware, on every backend.

    SQLite
    silently drops tzinfo on read-back, verified empirically there) —
    duplicated here rather than shared so the two services stay independently
    deployable, with no import coupling between them.
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


def enable_sqlite_foreign_keys(engine: Engine) -> Engine:
    """SQLite ignores every `ondelete=` declared on a ForeignKey unless FK
    enforcement is turned on per-connection — without this, deleting a
    Portfolio/User in tests would silently leave orphaned Transaction/
    Instrument rows instead of cascading, while the same delete correctly
    cascades against Postgres in production/CI. Must be applied to every
    SQLite engine this app creates, including test fixtures (see
    tests/conftest.py)."""
    if engine.url.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def _make_engine():
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return enable_sqlite_foreign_keys(create_engine(settings.database_url, connect_args=connect_args, future=True))


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
