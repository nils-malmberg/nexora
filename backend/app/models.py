"""ORM models for the News & Events module.

Schema follows the minimal data model in specs/NEWS_AND_EVENTS.md: Asset,
Provider, NewsItem, Event, IngestionRun, plus the association/history tables
needed for asset tagging, duplicate/corroboration links, and auditable event
status changes. Timestamps are stored in UTC; timezone of *display* is kept
separately where the source event has its own timezone.

JSON columns use the portable `JSON` type (JSONB on Postgres, JSON1 on
SQLite) so the same models back both the Postgres deployment and the
SQLite-based test suite (see specs/ARCHITECTURE.md and specs/TESTING.md).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime

JSONType = JSON().with_variant(JSONB(), "postgresql")


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class Asset(Base):
    """Minimal reference table: this module does not own the full instrument
    domain (that belongs to the portfolio module, out of scope here)."""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(200))
    isin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    market: Mapped[str | None] = mapped_column(String(40), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (UniqueConstraint("symbol", "market", name="uq_asset_symbol_market"),)


class Provider(Base):
    """A configured, interchangeable data source. `config` never contains a
    secret value directly - only references (e.g. an env var name) that the
    adapter resolves at call time. See specs/SECURITY.md."""

    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    type: Mapped[str] = mapped_column(String(20))  # rss | json_api | calendar_ics
    enabled: Mapped[bool] = mapped_column(default=True)
    config: Mapped[dict] = mapped_column(JSONType, default=dict)
    capabilities: Mapped[dict] = mapped_column(JSONType, default=dict)
    license_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Health / circuit-breaker state (small enough to live on the row; see
    # app/pipeline/ingest.py for how it is updated).
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    circuit_state: Mapped[str] = mapped_column(String(12), default="closed")  # closed|open|half_open

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    feeds: Mapped[list[ProviderFeed]] = relationship(back_populates="provider", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("type in ('rss','json_api','calendar_ics')", name="ck_provider_type"),
        CheckConstraint("circuit_state in ('closed','open','half_open')", name="ck_provider_circuit_state"),
    )


class ProviderFeed(Base):
    """One concrete endpoint/feed for a provider, optionally scoped to a
    single asset (common for issuer RSS feeds); when asset_id is null the
    adapter attributes items via keyword/symbol matching (approximate,
    reflected in a lower asset match confidence)."""

    __tablename__ = "provider_feeds"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"))
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    url: Mapped[str] = mapped_column(String(1000))
    extra_config: Mapped[dict] = mapped_column(JSONType, default=dict)

    provider: Mapped[Provider] = relationship(back_populates="feeds")
    asset: Mapped[Asset | None] = relationship()


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"))

    kind: Mapped[str] = mapped_column(String(12))  # fact | synthesis | prediction
    category: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(500))
    excerpt: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    publication_at: Mapped[datetime] = mapped_column(UTCDateTime)
    event_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")

    url: Mapped[str] = mapped_column(String(1000))
    citation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provenance: Mapped[str] = mapped_column(String(200))

    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    relevance_breakdown: Mapped[dict] = mapped_column(JSONType, default=dict)

    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    freshness_at_collection: Mapped[str] = mapped_column(String(12), default="unknown")
    verification_status: Mapped[str] = mapped_column(String(16), default="unverified")

    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    raw_meta: Mapped[dict] = mapped_column(JSONType, default=dict)

    asset_links: Mapped[list[NewsItemAsset]] = relationship(
        back_populates="news_item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("kind in ('fact','synthesis','prediction')", name="ck_news_kind"),
        CheckConstraint(
            "category in ('resultats','dividende','reglementation','operation_titre',"
            "'gouvernance','marche','macro','autre')",
            name="ck_news_category",
        ),
        CheckConstraint(
            "verification_status in ('unverified','corroborated','corrected','retracted')",
            name="ck_news_verification_status",
        ),
        Index("ix_news_provider_hash", "provider_id", "content_hash"),
        Index("ix_news_publication_at", "publication_at"),
    )


class NewsItemAsset(Base):
    __tablename__ = "news_item_assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    news_item_id: Mapped[str] = mapped_column(ForeignKey("news_items.id", ondelete="CASCADE"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    match_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    match_method: Mapped[str] = mapped_column(String(16), default="explicit")  # explicit | keyword

    news_item: Mapped[NewsItem] = relationship(back_populates="asset_links")
    asset: Mapped[Asset] = relationship()

    __table_args__ = (UniqueConstraint("news_item_id", "asset_id", name="uq_news_item_asset"),)


class NewsItemRelation(Base):
    """Keeps `duplicate_of` and `corroborates` relations queryable instead of
    silently discarding an independent source, per NEWS_AND_EVENTS.md."""

    __tablename__ = "news_item_relations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    news_item_id: Mapped[str] = mapped_column(ForeignKey("news_items.id", ondelete="CASCADE"))
    related_news_item_id: Mapped[str] = mapped_column(ForeignKey("news_items.id", ondelete="CASCADE"))
    relation_type: Mapped[str] = mapped_column(String(16))  # duplicate_of | corroborates
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint("relation_type in ('duplicate_of','corroborates')", name="ck_relation_type"),
        UniqueConstraint("news_item_id", "related_news_item_id", "relation_type", name="uq_news_relation"),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"))

    type: Mapped[str] = mapped_column(String(40))
    starts_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    period_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    status: Mapped[str] = mapped_column(String(16), default="unknown")

    amount: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)

    last_verified_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    content_hash: Mapped[str] = mapped_column(String(64), index=True)

    asset: Mapped[Asset] = relationship()
    sources: Mapped[list[EventSource]] = relationship(back_populates="event", cascade="all, delete-orphan")
    status_history: Mapped[list[EventStatusHistory]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="EventStatusHistory.changed_at"
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('confirme','previsionnel','reporte','annule','unknown')", name="ck_event_status"
        ),
        Index("ix_event_asset_starts", "asset_id", "starts_at"),
    )


class EventSource(Base):
    __tablename__ = "event_sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(1000))
    citation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    is_primary: Mapped[bool] = mapped_column(default=True)

    event: Mapped[Event] = relationship(back_populates="sources")


class EventStatusHistory(Base):
    __tablename__ = "event_status_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    old_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_status: Mapped[str] = mapped_column(String(16))
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    event: Mapped[Event] = relationship(back_populates="status_history")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="running")  # running|success|partial|failed
    counts: Mapped[dict] = mapped_column(JSONType, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)

    __table_args__ = (
        CheckConstraint("status in ('running','success','partial','failed')", name="ck_run_status"),
        Index("ix_run_provider_started", "provider_id", "started_at"),
    )
