"""FIFO position/cash accounting and valuation.

Implements specs/PRODUCT_SPEC.md's "valeur = quantité × prix applicable +
cash ; un prix absent est signalé, jamais inventé" — extended to FX: a
position whose currency differs from the portfolio's base currency is
converted with a dated reference rate (app/domain/fx.py) whose provenance is
returned alongside; when no rate is known it is listed and excluded from the
aggregate total (see ValuationView.unconverted_currencies), never converted
at a fabricated rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.domain.fx import Conversion, convert
from app.models import Instrument, OhlcBar, Portfolio, PositionLot, PricePoint, PrivateValuation, Transaction
from app.schemas.transactions import TransactionCreate

LOT_AFFECTING_TYPES = ("achat", "vente", "split")


class DuplicateTransactionError(Exception):
    """Raised by `apply_transaction` when `external_id` already exists for
    this portfolio. A distinct type from ValueError (oversell/split errors)
    so callers can treat it differently: the manual API rejects it (409),
    while CSV import treats a repeat import as an idempotent no-op (skipped,
    not an error) — specs/PORTFOLIO_IMPORTS.md: "Les imports répétés
    utilisent external_id ou empreinte canonique"."""

    def __init__(self, message: str, existing_transaction_id: str):
        super().__init__(message)
        self.existing_transaction_id = existing_transaction_id


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


def existing_lot_transactions(db: Session, portfolio_id: str, instrument_id: str) -> list[Transaction]:
    """Public entry point for CSV import (app/domain/csv_import.py), which
    needs to replay an instrument's existing transactions together with new,
    not-yet-applied batch rows to detect a sell-short spanning both."""
    return _lot_transactions(db, portfolio_id, instrument_id)


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


def record_private_valuation(
    db: Session,
    instrument: Instrument,
    valuation_date: datetime,
    amount: Decimal,
    currency: str,
    method: str,
    confidence: Decimal,
    note: str | None,
) -> PrivateValuation:
    """Shared by `POST /instruments/{id}/private-valuations`
    (app/api/routers/instruments.py) and `apply_transaction` below, so a
    private valuation always has exactly one code path regardless of whether
    it arrived through that dedicated endpoint, the manual transaction API,
    or CSV import."""
    if instrument.asset_class != "actif_prive":
        raise ValueError("private valuations are only valid for asset_class='actif_prive'")

    valuation = PrivateValuation(
        instrument_id=instrument.id,
        valuation_date=valuation_date,
        valuation_amount=amount,
        currency=currency,
        method=method,
        confidence=confidence,
        note=note,
    )
    db.add(valuation)
    # Feeds the position/valuation engine the same way a market PricePoint
    # does (see latest_price below).
    db.add(
        PricePoint(
            instrument_id=instrument.id,
            as_of=valuation_date,
            price=amount,
            currency=currency,
            source="private_valuation",
            is_estimate=True,
        )
    )
    return valuation


def apply_transaction(
    db: Session, portfolio: Portfolio, instrument: Instrument | None, payload: TransactionCreate
) -> Transaction:
    """Single source of truth for turning a validated `TransactionCreate`
    into persisted rows — used by both the manual
    `POST /portfolios/{id}/transactions` endpoint and CSV import, so the two
    paths can never drift apart on business rules (dedup, oversell, private
    valuations).

    Raises `DuplicateTransactionError` (external_id already used in this
    portfolio) or `ValueError` (oversell, bad split ratio, private valuation
    on a non-`actif_prive` instrument) — the caller decides what that means
    for its own flow (manual API: reject; CSV: report the row and continue).
    Does not commit; the caller controls the transaction boundary.
    """
    if payload.external_id:
        existing = db.scalars(
            select(Transaction).where(
                Transaction.portfolio_id == portfolio.id, Transaction.external_id == payload.external_id
            )
        ).first()
        if existing is not None:
            raise DuplicateTransactionError(
                f"a transaction with external_id={payload.external_id!r} already exists", existing.id
            )

    tx = Transaction(
        portfolio_id=portfolio.id,
        instrument_id=instrument.id if instrument else None,
        type=payload.type,
        trade_date=payload.trade_date,
        quantity=payload.quantity,
        unit_price=payload.unit_price,
        currency=payload.currency,
        fees=payload.fees,
        account=payload.account,
        external_id=payload.external_id,
        note=payload.note,
    )
    db.add(tx)
    db.flush()  # assigns tx.id, and makes the row visible to rebuild_lots' query below

    if instrument and payload.type in LOT_AFFECTING_TYPES:
        rebuild_lots(db, portfolio.id, instrument.id)  # may raise ValueError

    if payload.type == "valorisation_privee":
        if instrument is None:
            raise ValueError("valorisation_privee requires an instrument")  # enforced by TransactionCreate already
        record_private_valuation(
            db,
            instrument,
            valuation_date=payload.trade_date,
            amount=payload.unit_price,
            currency=payload.currency,
            method=payload.method,
            confidence=payload.confidence if payload.confidence is not None else Decimal("0.5"),
            note=payload.note,
        )

    return tx


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


@dataclass
class PriceObs:
    """The price applicable to a position: the freshest of the latest quote
    (`PricePoint`, live/manual/private) and the latest daily bar close
    (`OhlcBar`) at or before `as_of`."""

    price: Decimal
    currency: str
    as_of: datetime
    source: str
    is_estimate: bool = False
    is_delayed: bool = False


def latest_observation(db: Session, instrument_id: str, as_of: datetime | None = None) -> PriceObs | None:
    point_query = select(PricePoint).where(PricePoint.instrument_id == instrument_id)
    bar_query = select(OhlcBar).where(OhlcBar.instrument_id == instrument_id)
    if as_of is not None:
        point_query = point_query.where(PricePoint.as_of <= as_of)
        bar_query = bar_query.where(OhlcBar.as_of <= as_of)
    point = db.scalars(point_query.order_by(PricePoint.as_of.desc()).limit(1)).first()
    bar = db.scalars(bar_query.order_by(OhlcBar.as_of.desc()).limit(1)).first()
    candidates: list[PriceObs] = []
    if point is not None:
        candidates.append(
            PriceObs(
                price=to_decimal(point.price),
                currency=point.currency,
                as_of=point.as_of,
                source=point.source,
                is_estimate=point.is_estimate,
                is_delayed=point.is_delayed,
            )
        )
    if bar is not None:
        candidates.append(
            PriceObs(
                price=to_decimal(bar.close),
                currency=bar.currency,
                as_of=bar.as_of,
                source=bar.source,
                is_estimate=False,
                is_delayed=True,
            )
        )
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.as_of)


def latest_price(db: Session, instrument_id: str) -> PriceObs | None:
    return latest_observation(db, instrument_id)


def freshness_status(price: PriceObs | None, now: datetime | None = None) -> str:
    if price is None:
        return "manquant"
    if price.is_estimate:
        return "estime"
    age = (now or datetime.now(UTC)) - price.as_of
    if age.total_seconds() > settings.price_freshness_hours * 3600:
        return "differe"
    return "a_jour"


@dataclass
class PositionView:
    instrument: Instrument
    quantity: Decimal
    average_unit_cost: Decimal
    cost_currency: str
    currency: str
    price: PriceObs | None
    market_value: Decimal | None
    freshness: str
    matches_base_currency: bool
    conversion: Conversion | None = None

    @property
    def market_value_base(self) -> Decimal | None:
        if self.market_value is None:
            return None
        if self.matches_base_currency:
            return self.market_value
        return self.conversion.amount if self.conversion else None

    @property
    def cost_basis(self) -> Decimal:
        return quantize_money(self.quantity * self.average_unit_cost)

    @property
    def unrealized_pnl(self) -> Decimal | None:
        """In the position's price currency; only meaningful when the lots'
        cost currency is the same (otherwise None rather than mixing)."""
        if self.market_value is None or self.cost_currency != self.currency:
            return None
        return quantize_money(self.market_value - self.cost_basis)


def build_position_view(
    db: Session,
    portfolio: Portfolio,
    instrument: Instrument,
    lots: list,
    *,
    as_of: datetime | None = None,
) -> PositionView | None:
    total_quantity = sum((to_decimal(lot.quantity_remaining) for lot in lots), Decimal("0"))
    if total_quantity <= 0:
        return None
    total_cost = sum((to_decimal(lot.quantity_remaining) * to_decimal(lot.unit_cost) for lot in lots), Decimal("0"))
    average_unit_cost = quantize_money(total_cost / total_quantity)
    cost_currency = lots[0].currency if lots else instrument.currency

    price = latest_observation(db, instrument.id, as_of)
    market_value = quantize_money(total_quantity * price.price) if price is not None else None
    price_currency = price.currency if price is not None else instrument.currency
    matches = price_currency == portfolio.base_currency
    conversion = None
    if market_value is not None and not matches:
        conversion = convert(db, market_value, price_currency, portfolio.base_currency, as_of)
    return PositionView(
        instrument=instrument,
        quantity=total_quantity,
        average_unit_cost=average_unit_cost,
        cost_currency=cost_currency,
        currency=price_currency,
        price=price,
        market_value=market_value,
        freshness=freshness_status(price, as_of),
        matches_base_currency=matches,
        conversion=conversion,
    )


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
    for instrument_id in sorted(instrument_ids):
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
        view = build_position_view(db, portfolio, instrument, lots)
        if view is not None:
            views.append(view)
    views.sort(key=lambda v: v.instrument.symbol)  # deterministic, and what a table expects
    return views


@dataclass
class FxNote:
    currency: str
    rate: Decimal
    rate_as_of: datetime
    source: str


@dataclass
class ValuationView:
    base_currency: str
    cash: Decimal
    cash_by_currency: dict[str, Decimal]
    positions_value: Decimal
    total_value: Decimal
    unconverted_currencies: list[str]
    has_missing_prices: bool
    fx_rates: list[FxNote]


def aggregate_valuation(
    db: Session,
    portfolio: Portfolio,
    positions: list[PositionView],
    cash_by_currency: dict[str, Decimal],
    as_of: datetime | None = None,
) -> ValuationView:
    """Shared by the live valuation and the historical (`as_of`) one so both
    apply exactly the same FX and missing-price rules."""
    positions_value = Decimal("0")
    unconverted: set[str] = set()
    has_missing_prices = False
    fx_notes: dict[str, FxNote] = {}

    for position in positions:
        if position.market_value is None:
            has_missing_prices = True
            continue
        value_base = position.market_value_base
        if value_base is None:
            unconverted.add(position.currency)
            continue
        positions_value += value_base
        if position.conversion is not None and position.currency not in fx_notes:
            c = position.conversion
            fx_notes[position.currency] = FxNote(position.currency, c.rate, c.rate_as_of, c.source)

    cash = cash_by_currency.get(portfolio.base_currency, Decimal("0"))
    for currency, balance in cash_by_currency.items():
        if currency == portfolio.base_currency or balance == 0:
            continue
        conversion = convert(db, balance, currency, portfolio.base_currency, as_of)
        if conversion is None:
            unconverted.add(currency)
            continue
        cash += conversion.amount
        if currency not in fx_notes:
            fx_notes[currency] = FxNote(currency, conversion.rate, conversion.rate_as_of, conversion.source)

    return ValuationView(
        base_currency=portfolio.base_currency,
        cash=quantize_money(cash),
        cash_by_currency=cash_by_currency,
        positions_value=quantize_money(positions_value),
        total_value=quantize_money(cash + positions_value),
        unconverted_currencies=sorted(unconverted),
        has_missing_prices=has_missing_prices,
        fx_rates=sorted(fx_notes.values(), key=lambda n: n.currency),
    )


def compute_valuation(db: Session, portfolio: Portfolio, positions: list[PositionView] | None = None) -> ValuationView:
    cash_by_currency = cash_balance_by_currency(db, portfolio.id)
    if positions is None:
        positions = compute_positions(db, portfolio)
    return aggregate_valuation(db, portfolio, positions, cash_by_currency)
