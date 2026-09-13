"""Currency conversion with provenance.

A converted amount always travels with the rate used, its date and its
source; when no rate is available the amount stays *unconverted* and is
listed separately (never converted at a made-up rate) — the FX counterpart
of "un prix absent est signalé, jamais inventé" (specs/PRODUCT_SPEC.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.market import service as market_service

MONEY_QUANTUM = Decimal("0.000001")


@dataclass
class Conversion:
    amount: Decimal
    rate: Decimal
    rate_as_of: datetime
    source: str
    from_currency: str
    to_currency: str


def convert(db: Session, amount: Decimal, from_currency: str, to_currency: str, as_of: datetime | None = None):
    """Returns a `Conversion`, or None when no rate is known for the pair."""
    if from_currency == to_currency:
        return Conversion(
            amount=amount,
            rate=Decimal("1"),
            rate_as_of=as_of or datetime.now(UTC),
            source="identity",
            from_currency=from_currency,
            to_currency=to_currency,
        )
    rate = market_service.get_fx_rate(db, from_currency, to_currency, as_of)
    if rate is None:
        return None
    r = Decimal(str(rate.rate))
    return Conversion(
        amount=(amount * r).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP),
        rate=r,
        rate_as_of=rate.as_of,
        source=rate.source,
        from_currency=from_currency,
        to_currency=to_currency,
    )


def prepare_fx(db: Session, currencies: set[str], base_currency: str, start: datetime, end: datetime) -> None:
    """Warm the FX cache for a date range in one provider call per pair, so a
    valuation history over hundreds of dates doesn't trigger hundreds of
    lookups."""
    for currency in currencies:
        if currency != base_currency:
            market_service.ensure_fx_series(db, currency, base_currency, start, end)
