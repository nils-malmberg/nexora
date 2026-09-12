"""ORM models for the Portfolio core module.

Schema follows the minimal domain model in specs/ARCHITECTURE.md: User,
Portfolio, Instrument, Transaction, PositionLot, PricePoint, PrivateValuation,
ImportJob (added in a follow-up PR alongside CSV import), AuditEvent,
ProviderCredentialRef.

Money is always `Numeric`, never `float` (specs/ARCHITECTURE.md: "montants
décimaux, jamais flottants pour les valeurs financières"). Timestamps are UTC
via the local `UTCDateTime` type (see app/db.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
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

ASSET_CLASSES = ("action", "etf", "crypto", "obligation", "actif_prive")
TRANSACTION_TYPES = (
    "achat",
    "vente",
    "dividende",
    "coupon",
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
CASH_ONLY_TRANSACTION_TYPES = ("dividende", "coupon", "depot", "retrait")


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reference_currency: Mapped[str] = mapped_column(String(8), default="EUR")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class UserSession(Base):
    """An opaque, server-revocable session (see app/security.py). Only the
    SHA-256 hash of the token is stored, mirroring how a password would never
    be stored in plaintext — a leaked DB row alone cannot be replayed as a
    cookie."""

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


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    base_currency: Mapped[str] = mapped_column(String(8), default="EUR")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship()


class Instrument(Base):
    """Tenant-scoped in V1: each user manages their own instrument catalog.

    A shared/global catalog (searchable across users, enriched by a real
    external reference source) is deferred — see the plan's note on not
    wiring a real market-data provider in this PR."""

    __tablename__ = "instruments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    asset_class: Mapped[str] = mapped_column(String(16))
    isin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    currency: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint(f"asset_class in {ASSET_CLASSES!r}", name="ck_instrument_asset_class"),
        UniqueConstraint("user_id", "symbol", name="uq_instrument_user_symbol"),
    )


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

    # A reversal never edits or deletes the original row (specs/PRODUCT_SPEC.md:
    # "immuable"); it excludes it from every computation (see
    # app/domain/positions.py) and leaves an audited reason, rather than
    # inserting a synthetic offsetting entry that FIFO lot matching could
    # misallocate against the wrong lot when other transactions exist between
    # the original and its correction.
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


class PricePoint(Base):
    __tablename__ = "price_points"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime)
    price: Mapped[float] = mapped_column(Numeric(20, 6))
    currency: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(40), default="manual")
    is_estimate: Mapped[bool] = mapped_column(default=False)
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (Index("ix_price_point_instrument_as_of", "instrument_id", "as_of"),)


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


class AuditEvent(Base):
    """Append-only audit trail for sensitive actions (login, portfolio/account
    deletion, transaction reversal) — specs/SECURITY.md incident-response and
    specs/PRODUCT_SPEC.md audit requirements."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    # SET NULL, not CASCADE: the row this event is about (a user or
    # portfolio) may legitimately be deleted later - the audit trail must
    # survive that deletion (with the reference nulled out) rather than being
    # deleted itself or blocking the deletion via a dangling FK.
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    portfolio_id: Mapped[str | None] = mapped_column(ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_metadata: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (Index("ix_audit_event_user_created", "user_id", "created_at"),)


class ProviderCredentialRef(Base):
    """Which market-data provider is active, referencing only the *name* of
    the env var holding its secret — never the secret itself, mirroring the
    News & Events module's `Provider.config` convention. Empty/unused until a
    real provider is confirmed and configured (see specs/DATA_SOURCES.md)."""

    __tablename__ = "provider_credential_refs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    provider_name: Mapped[str] = mapped_column(String(60), unique=True)
    env_var: Mapped[str | None] = mapped_column(String(120), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    license_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
