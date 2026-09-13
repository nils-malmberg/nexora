"""ORM models for the whole NeXora application (single database).

One schema, one Alembic history, grouped by domain:

- Identity: User, UserSession, AuditEvent
- Portfolio: Portfolio, Transaction, PositionLot, PrivateValuation, ImportJob
- Market: Instrument (shared catalog + per-user private assets), PricePoint,
  OhlcBar, FxRate, WatchlistItem, MarketProvider
- News & events: Provider, ProviderFeed, NewsItem, NewsItemAsset,
  NewsItemRelation, Event, EventSource, EventStatusHistory, IngestionRun
- Prediction (experimental): PredictionExperiment

Money is always `Numeric`, never `float` (specs/ARCHITECTURE.md). Timestamps
are UTC via `UTCDateTime` (see app/db.py). JSON columns use the portable JSON
type (JSONB on Postgres, JSON1 on SQLite) so the same models back both the
Postgres deployment and the SQLite-based test suite.
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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime

JSONType = JSON().with_variant(JSONB(), "postgresql")

ASSET_CLASSES = ("action", "etf", "crypto", "obligation", "actif_prive", "indice", "devise")
TRANSACTION_TYPES = (
    "achat",
    "vente",
    "dividende",
    "coupon",
    "interet",
    "frais",
    "depot",
    "retrait",
    "transfert",
    "split",
    "valorisation_privee",
)
# Transaction types that represent a pure cash movement (no instrument
# quantity effect): the CSV schema in specs/PORTFOLIO_IMPORTS.md uses the same
# `quantity`/`unit_price` columns for every type, so for these the convention
# is quantity == 1 and unit_price == the cash amount (see app/domain/positions.py).
# `interet` (interest paid on cash) and `frais` (a standalone fee such as a
# custody fee) are *internal* cash movements like dividends - they change the
# value without being an external contribution/withdrawal (TWR/MWR).
CASH_ONLY_TRANSACTION_TYPES = ("dividende", "coupon", "interet", "frais", "depot", "retrait")

MARKET_PROVIDER_NAMES = ("yahoo", "coingecko", "finnhub", "frankfurter", "fixture", "null")


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reference_currency: Mapped[str] = mapped_column(String(8), default="EUR")
    display_timezone: Mapped[str] = mapped_column(String(64), default="Europe/Paris")
    is_active: Mapped[bool] = mapped_column(default=True)
    # The first registered account (or any email listed in NEXORA_ADMIN_EMAILS)
    # administers providers and ingestion; there is no separate admin key.
    is_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class UserSession(Base):
    """An opaque, server-revocable session (see app/security.py). Only the
    SHA-256 hash of the token is stored — a leaked DB row alone cannot be
    replayed as a cookie."""

    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)

    user: Mapped[User] = relationship()


class AuditEvent(Base):
    """Append-only audit trail for sensitive actions (login, deletions,
    transaction reversal, provider changes, prediction runs)."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    # SET NULL, not CASCADE: the audit trail must survive deletion of what it
    # is about, rather than being deleted itself or blocking the deletion.
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    portfolio_id: Mapped[str | None] = mapped_column(ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_metadata: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (Index("ix_audit_event_user_created", "user_id", "created_at"),)


# ---------------------------------------------------------------------------
# Market catalog and prices
# ---------------------------------------------------------------------------


class Instrument(Base):
    """One row per tradable/valued thing.

    - `user_id IS NULL`: a *shared* catalog entry discovered through a market
      data provider (`provider` + `provider_symbol` identify it there). Every
      user sees it; nobody owns it.
    - `user_id` set: a *private* instrument (typically an `actif_prive`, or a
      manually-defined bond) visible only to its owner.

    News and events attach to the same rows (specs/NEWS_AND_EVENTS.md's
    `Asset` is this table), so an instrument page can show quote, chart,
    positions, news and calendar together.
    """

    __tablename__ = "instruments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(200))
    asset_class: Mapped[str] = mapped_column(String(16))
    isin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(40), nullable=True)
    currency: Mapped[str] = mapped_column(String(8))
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    provider_symbol: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint(f"asset_class in {ASSET_CLASSES!r}", name="ck_instrument_asset_class"),
        UniqueConstraint("user_id", "symbol", name="uq_instrument_user_symbol"),
        UniqueConstraint("provider", "provider_symbol", name="uq_instrument_provider_symbol"),
    )

    def is_visible_to(self, user_id: str) -> bool:
        return self.user_id is None or self.user_id == user_id


class PricePoint(Base):
    """Latest-known price observations (one row per observation): a live
    quote from a provider, a manual entry, or a private valuation. Provenance
    (`source`), delay and estimate flags travel with the value."""

    __tablename__ = "price_points"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime)
    price: Mapped[float] = mapped_column(Numeric(20, 6))
    currency: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(40), default="manual")
    is_estimate: Mapped[bool] = mapped_column(default=False)
    is_delayed: Mapped[bool] = mapped_column(default=False)
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (Index("ix_price_point_instrument_as_of", "instrument_id", "as_of"),)


class OhlcBar(Base):
    """Historical bar from a provider (daily in V1). Never synthesised: a bar
    exists only if the source published it, and open/high/low stay NULL when
    the source only publishes closes (e.g. CoinGecko's daily market chart) —
    the chart then draws a line, not invented candles."""

    __tablename__ = "ohlc_bars"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    interval: Mapped[str] = mapped_column(String(8), default="1d")
    as_of: Mapped[datetime] = mapped_column(UTCDateTime)
    open: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    high: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    low: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    close: Mapped[float] = mapped_column(Numeric(20, 6))
    volume: Mapped[float | None] = mapped_column(Numeric(28, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(40))
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("instrument_id", "interval", "as_of", name="uq_ohlc_instrument_interval_as_of"),
        CheckConstraint("low IS NULL OR high IS NULL OR low <= high", name="ck_ohlc_low_le_high"),
    )


class FxRate(Base):
    """Daily reference exchange rate (`quote` per 1 `base`), with provenance."""

    __tablename__ = "fx_rates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    base: Mapped[str] = mapped_column(String(8))
    quote: Mapped[str] = mapped_column(String(8))
    as_of: Mapped[datetime] = mapped_column(UTCDateTime)
    rate: Mapped[float] = mapped_column(Numeric(20, 8))
    source: Mapped[str] = mapped_column(String(40))
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("base", "quote", "as_of", name="uq_fx_base_quote_as_of"),
        Index("ix_fx_pair_as_of", "base", "quote", "as_of"),
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    instrument: Mapped[Instrument] = relationship()

    __table_args__ = (UniqueConstraint("user_id", "instrument_id", name="uq_watchlist_user_instrument"),)


class MarketProvider(Base):
    """Runtime state of one market-data provider (the `ProviderCredentialRef`
    of specs/ARCHITECTURE.md): enabled flag, circuit-breaker state, and the
    *name* of the env var holding its key — never the key itself. Rows are
    created lazily by app/market/registry.py."""

    __tablename__ = "market_providers"

    name: Mapped[str] = mapped_column(String(20), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    env_var: Mapped[str | None] = mapped_column(String(120), nullable=True)
    license_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    circuit_state: Mapped[str] = mapped_column(String(12), default="closed")
    disabled_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint("circuit_state in ('closed','open','half_open')", name="ck_market_provider_circuit"),
    )


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    base_currency: Mapped[str] = mapped_column(String(8), default="EUR")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship()


class Transaction(Base):
    """Immutable once created: a correction sets `reversed_at`/`reversal_reason`
    rather than editing or deleting the original row — specs/PRODUCT_SPEC.md:
    "Une transaction validée est immuable"."""

    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), nullable=True)

    type: Mapped[str] = mapped_column(String(20))
    trade_date: Mapped[datetime] = mapped_column(UTCDateTime)
    quantity: Mapped[float] = mapped_column(Numeric(24, 8))
    unit_price: Mapped[float] = mapped_column(Numeric(20, 6))
    currency: Mapped[str] = mapped_column(String(8))
    fees: Mapped[float] = mapped_column(Numeric(20, 6), default=0)

    account: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    reversed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reversal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    instrument: Mapped[Instrument | None] = relationship()

    __table_args__ = (
        CheckConstraint(f"type in {TRANSACTION_TYPES!r}", name="ck_transaction_type"),
        UniqueConstraint("portfolio_id", "external_id", name="uq_transaction_portfolio_external_id"),
        Index("ix_transaction_portfolio_trade_date", "portfolio_id", "trade_date"),
    )


class PositionLot(Base):
    """Materialized FIFO lot, rebuilt deterministically from the transaction
    log for one (portfolio, instrument) pair whenever it changes — see
    app/domain/positions.py. Never hand-edited."""

    __tablename__ = "position_lots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime)
    quantity_remaining: Mapped[float] = mapped_column(Numeric(24, 8))
    unit_cost: Mapped[float] = mapped_column(Numeric(20, 6))
    currency: Mapped[str] = mapped_column(String(8))
    source_transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"))


class PrivateValuation(Base):
    __tablename__ = "private_valuations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    valuation_date: Mapped[datetime] = mapped_column(UTCDateTime)
    valuation_amount: Mapped[float] = mapped_column(Numeric(20, 6))
    currency: Mapped[str] = mapped_column(String(8))
    method: Mapped[str] = mapped_column(String(200))
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), default=0.5)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


IMPORT_JOB_STATUSES = ("draft", "previewed", "committed")


class ImportJob(Base):
    """One CSV import, tracked through draft → previewed → committed. The raw
    file bytes are never written anywhere; `raw_rows` (parsed rows) is
    cleared once committed and only the structured report is kept."""

    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(260))
    status: Mapped[str] = mapped_column(String(12), default="draft")
    # Broker export profile applied before the generic mapping (see
    # app/domain/broker_presets.py); None = generic CSV.
    preset: Mapped[str | None] = mapped_column(String(32), nullable=True)
    delimiter: Mapped[str] = mapped_column(String(4))
    encoding: Mapped[str] = mapped_column(String(40))
    column_mapping: Mapped[dict] = mapped_column(JSONType, default=dict)
    default_timezone: Mapped[str] = mapped_column(String(40), default="UTC")
    raw_rows: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    row_results: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    total_rows: Mapped[int] = mapped_column(default=0)
    valid_count: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
    duplicate_count: Mapped[int] = mapped_column(default=0)
    inserted_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    previewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    __table_args__ = (CheckConstraint(f"status in {IMPORT_JOB_STATUSES!r}", name="ck_import_job_status"),)


# ---------------------------------------------------------------------------
# News & events (specs/NEWS_AND_EVENTS.md)
# ---------------------------------------------------------------------------


class Provider(Base):
    """A configured, interchangeable news/event source. `config` never holds
    a secret value — only references (an env var name) resolved at call time."""

    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    type: Mapped[str] = mapped_column(String(20))  # rss | json_api | calendar_ics
    enabled: Mapped[bool] = mapped_column(default=True)
    config: Mapped[dict] = mapped_column(JSONType, default=dict)
    capabilities: Mapped[dict] = mapped_column(JSONType, default=dict)
    license_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

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
    """One concrete endpoint/feed for a provider, optionally bound to a single
    instrument (common for issuer feeds); when unbound the adapter attributes
    items via keyword/symbol matching (lower match confidence)."""

    __tablename__ = "provider_feeds"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"))
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id", ondelete="SET NULL"), nullable=True)
    url: Mapped[str] = mapped_column(String(1000))
    extra_config: Mapped[dict] = mapped_column(JSONType, default=dict)

    provider: Mapped[Provider] = relationship(back_populates="feeds")
    instrument: Mapped[Instrument | None] = relationship()


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

    asset_links: Mapped[list[NewsItemAsset]] = relationship(back_populates="news_item", cascade="all, delete-orphan")

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
    __tablename__ = "news_item_instruments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    news_item_id: Mapped[str] = mapped_column(ForeignKey("news_items.id", ondelete="CASCADE"))
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"))
    match_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    match_method: Mapped[str] = mapped_column(String(16), default="explicit")  # explicit | keyword

    news_item: Mapped[NewsItem] = relationship(back_populates="asset_links")
    instrument: Mapped[Instrument] = relationship()

    __table_args__ = (UniqueConstraint("news_item_id", "instrument_id", name="uq_news_item_instrument"),)


class NewsItemRelation(Base):
    """Keeps `duplicate_of` and `corroborates` relations queryable instead of
    silently discarding an independent source."""

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
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"))
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

    instrument: Mapped[Instrument] = relationship()
    sources: Mapped[list[EventSource]] = relationship(back_populates="event", cascade="all, delete-orphan")
    status_history: Mapped[list[EventStatusHistory]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="EventStatusHistory.changed_at"
    )

    __table_args__ = (
        CheckConstraint("status in ('confirme','previsionnel','reporte','annule','unknown')", name="ck_event_status"),
        Index("ix_event_instrument_starts", "instrument_id", "starts_at"),
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


# ---------------------------------------------------------------------------
# Prediction (experimental — specs/PREDICTION.md)
# ---------------------------------------------------------------------------

PREDICTION_STATUSES = ("pending", "running", "completed", "failed")


class PredictionExperiment(Base):
    """One user-owned, reproducible experiment: configuration, dataset
    fingerprint, walk-forward metrics per model and per fold, and the last
    out-of-sample forecast with its uncertainty band. Model binaries are not
    stored — an experiment is fully re-creatable from (config, dataset hash,
    code version, seed), which is the governance unit specs/PREDICTION.md asks
    for. Nothing here is ever an order, a target price or a recommendation."""

    __tablename__ = "prediction_experiments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(12), default="pending")
    config: Mapped[dict] = mapped_column(JSONType, default=dict)
    code_version: Mapped[str] = mapped_column(String(40))
    dataset_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_start: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    dataset_end: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    n_observations: Mapped[int] = mapped_column(default=0)
    metrics: Mapped[dict] = mapped_column(JSONType, default=dict)
    folds: Mapped[list] = mapped_column(JSONType, default=list)
    predictions: Mapped[list] = mapped_column(JSONType, default=list)
    latest_forecast: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    trained_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (CheckConstraint(f"status in {PREDICTION_STATUSES!r}", name="ck_prediction_status"),)
