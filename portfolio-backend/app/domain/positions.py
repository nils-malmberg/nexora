"""FIFO position/cash accounting and valuation.

Implements specs/PRODUCT_SPEC.md's "valeur = quantité × prix applicable +
cash ; un prix absent est signalé, jamais inventé" — extended to FX: a
position whose currency differs from the portfolio's base currency is never
silently converted with a fabricated rate, only listed and excluded from the
aggregate total (see ValuationView.unconverted_currencies). Wiring a real FX
rate source follows the same provider-confirmation process as a market-data
adapter, and is deferred to a later PR.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Instrument, Portfolio, PositionLot, PricePoint, Transaction

LOT_AFFECTING_TYPES = ("achat", "vente", "split")

# Matches the DB columns' declared scale (Numeric(20,6) for money,
# Numeric(24,8) for quantities). Chained Decimal arithmetic (multiplication
# sums the operands' scales, e.g. an 8dp quantity times a 6dp price gives a
# 14dp product) never rounds on its own - without quantizing at each
# computed value, precision would keep growing with every multiplication and
# the same figure could render differently depending on incidental
# SQLAlchemy identity-map caching (raw, just-submitted value) vs a fresh
# round-trip through a NUMERIC column (DB-padded to the declared scale).
MONEY_QUANTUM = Decimal("0.000001")
QUANTITY_QUANTUM = Decimal("0.00000001")


def to_decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def quantize_quantity(value: Decimal) -> Decimal:
    return value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


def cash_delta(tx: Transaction) -> Decimal:
    """Signed cash effect of one transaction. Convention for cash-only types
    (dividende/coupon/depot/retrait): `quantity` is always 1 and `unit_price`
    carries the cash amount — enforced at the API layer (app/schemas)."""
    quantity = to_decimal(tx.quantity)
    unit_price = to_decimal(tx.unit_price)
    fees = to_decimal(tx.fees or 0)

    if tx.type == "achat":
        effect = -(quantity * unit_price)
    elif tx.type == "vente":
        effect = quantity * unit_price
    elif tx.type in ("dividende", "coupon", "depot"):
        effect = unit_price
    elif tx.type == "retrait":
        effect = -unit_price
    else:  # transfert, split, valorisation_privee: no direct cash effect
        effect = Decimal("0")
    return quantize_money(effect - fees)


@dataclass
class LotState:
    opened_at: datetime
    quantity_remaining: Decimal
    unit_cost: Decimal
    currency: str
    source_transaction_id: str


def replay_lots(transactions: list[Transaction]) -> list[LotState]:
    """FIFO replay for one instrument's ordered, non-reversed transactions.

    Raises ValueError if a sell would take quantity negative —
    specs/PORTFOLIO_IMPORTS.md: "Les ventes ne peuvent pas créer une quantité
    négative sans correction signalée". The caller turns this into a 422."""
    lots: list[LotState] = []
    for tx in transactions:
        quantity = to_decimal(tx.quantity)
        if tx.type == "achat":
            total_cost = quantity * to_decimal(tx.unit_price) + to_decimal(tx.fees or 0)
            unit_cost = total_cost / quantity if quantity else Decimal("0")
            lots.append(
                LotState(
                    opened_at=tx.trade_date,
                    quantity_remaining=quantize_quantity(quantity),
                    unit_cost=quantize_money(unit_cost),
                    currency=tx.currency,
                    source_transaction_id=tx.id,
                )
            )
        elif tx.type == "vente":
            remaining_to_sell = quantity
            for lot in lots:
                if remaining_to_sell <= 0:
                    break
                if lot.quantity_remaining <= 0:
                    continue
                consumed = min(lot.quantity_remaining, remaining_to_sell)
                lot.quantity_remaining -= consumed
                remaining_to_sell -= consumed
            if remaining_to_sell > 0:
                held = quantity - remaining_to_sell
                raise ValueError(
                    f"sell quantity ({quantity}) exceeds available position ({held}) at transaction {tx.id}"
                )
        elif tx.type == "split":
            ratio = quantity  # convention: new shares per old share (e.g. 2 for a 2-for-1 split)
            if ratio <= 0:
                raise ValueError(f"split ratio must be positive (transaction {tx.id})")
            for lot in lots:
                lot.quantity_remaining = quantize_quantity(lot.quantity_remaining * ratio)
                lot.unit_cost = quantize_money(lot.unit_cost / ratio)
        # dividende/coupon/depot/retrait/transfert/valorisation_privee: no lot effect
    return [lot for lot in lots if lot.quantity_remaining > 0]


def _lot_transactions(db: Session, portfolio_id: str, instrument_id: str) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.instrument_id == instrument_id,
                Transaction.reversed_at.is_(None),
                Transaction.type.in_(LOT_AFFECTING_TYPES),
            )
            .order_by(Transaction.trade_date, Transaction.created_at)
        )
    )


def available_quantity(db: Session, portfolio_id: str, instrument_id: str) -> Decimal:
    """Quantity currently held, computed without persisting — used to
    validate a prospective sell before committing it."""
    lots = replay_lots(_lot_transactions(db, portfolio_id, instrument_id))
    return sum((lot.quantity_remaining for lot in lots), Decimal("0"))


def rebuild_lots(db: Session, portfolio_id: str, instrument_id: str) -> list[PositionLot]:
    """Deletes and rebuilds this (portfolio, instrument) pair's PositionLot
    rows from the transaction log. Called after every write affecting the
    pair — cheap and correct at V1 (personal-dashboard) scale."""
    lot_states = replay_lots(_lot_transactions(db, portfolio_id, instrument_id))

    db.execute(
        delete(PositionLot).where(PositionLot.portfolio_id == portfolio_id, PositionLot.instrument_id == instrument_id)
    )
    lots = [
        PositionLot(
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            opened_at=state.opened_at,
            quantity_remaining=state.quantity_remaining,
            unit_cost=state.unit_cost,
            currency=state.currency,
            source_transaction_id=state.source_transaction_id,
        )
        for state in lot_states
    ]
    db.add_all(lots)
    return lots


def cash_balance_by_currency(db: Session, portfolio_id: str) -> dict[str, Decimal]:
    """Cash is tracked per transaction currency, never blended: summing raw
    deltas across currencies (e.g. a EUR deposit and a USD stock purchase)
    would silently treat 1 EUR as worth 1 USD. Only the base-currency balance
    feeds `ValuationView.total_value`; the rest surfaces via
    `unconverted_currencies`, same principle as position FX handling above."""
    transactions = db.scalars(
        select(Transaction).where(
            Transaction.portfolio_id == portfolio_id,
            Transaction.reversed_at.is_(None),
        )
    )
    balances: dict[str, Decimal] = {}
    for tx in transactions:
        balances[tx.currency] = balances.get(tx.currency, Decimal("0")) + cash_delta(tx)
    return balances


def latest_price(db: Session, instrument_id: str) -> PricePoint | None:
    return db.scalars(
        select(PricePoint).where(PricePoint.instrument_id == instrument_id).order_by(PricePoint.as_of.desc()).limit(1)
    ).first()


def freshness_status(price: PricePoint | None) -> str:
    if price is None:
        return "manquant"
    if price.is_estimate:
        return "estime"
    age = datetime.now(UTC) - price.as_of
    if age.total_seconds() > settings.price_freshness_hours * 3600:
        return "differe"
    return "a_jour"


@dataclass
class PositionView:
    instrument: Instrument
    quantity: Decimal
    average_unit_cost: Decimal
    currency: str
    price: PricePoint | None
    market_value: Decimal | None
    freshness: str
    matches_base_currency: bool


def compute_positions(db: Session, portfolio: Portfolio) -> list[PositionView]:
    instrument_ids = {
        row[0]
        for row in db.execute(
            select(PositionLot.instrument_id)
            .where(PositionLot.portfolio_id == portfolio.id, PositionLot.quantity_remaining > 0)
            .distinct()
        )
    }
    views: list[PositionView] = []
    for instrument_id in instrument_ids:
        instrument = db.get(Instrument, instrument_id)
        if instrument is None:
            continue
        lots = list(
            db.scalars(
                select(PositionLot).where(
                    PositionLot.portfolio_id == portfolio.id,
                    PositionLot.instrument_id == instrument_id,
                    PositionLot.quantity_remaining > 0,
                )
            )
        )
        total_quantity = sum((to_decimal(lot.quantity_remaining) for lot in lots), Decimal("0"))
        total_cost = sum((to_decimal(lot.quantity_remaining) * to_decimal(lot.unit_cost) for lot in lots), Decimal("0"))
        average_unit_cost = quantize_money(total_cost / total_quantity) if total_quantity else Decimal("0")

        price = latest_price(db, instrument_id)
        market_value = quantize_money(total_quantity * to_decimal(price.price)) if price is not None else None

        views.append(
            PositionView(
                instrument=instrument,
                quantity=total_quantity,
                average_unit_cost=average_unit_cost,
                currency=instrument.currency,
                price=price,
                market_value=market_value,
                freshness=freshness_status(price),
                matches_base_currency=instrument.currency == portfolio.base_currency,
            )
        )
    return views


@dataclass
class ValuationView:
    base_currency: str
    cash: Decimal
    cash_by_currency: dict[str, Decimal]
    positions_value: Decimal
    total_value: Decimal
    unconverted_currencies: list[str]
    has_missing_prices: bool


def compute_valuation(db: Session, portfolio: Portfolio, positions: list[PositionView] | None = None) -> ValuationView:
    cash_by_currency = cash_balance_by_currency(db, portfolio.id)
    if positions is None:
        positions = compute_positions(db, portfolio)

    positions_value = Decimal("0")
    unconverted: set[str] = set()
    has_missing_prices = False
    for position in positions:
        if position.market_value is None:
            has_missing_prices = True
            continue
        if position.matches_base_currency:
            positions_value += position.market_value
        else:
            unconverted.add(position.currency)

    for currency in cash_by_currency:
        if currency != portfolio.base_currency:
            unconverted.add(currency)

    cash = cash_by_currency.get(portfolio.base_currency, Decimal("0"))

    return ValuationView(
        base_currency=portfolio.base_currency,
        cash=quantize_money(cash),
        cash_by_currency=cash_by_currency,
        positions_value=quantize_money(positions_value),
        total_value=quantize_money(cash + positions_value),
        unconverted_currencies=sorted(unconverted),
        has_missing_prices=has_missing_prices,
    )
