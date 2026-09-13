"""Realized gains and portfolio income.

Two reports a long-term investor reads once a year (and a tax return needs):

- **realized gains**: every sale matched FIFO against the lots it consumed
  (the very same replay as the open positions, see `replay_lots`), giving
  proceeds, cost basis and the realized P&L per sale, per year and per
  instrument;
- **income**: dividends, coupons and interest received, standalone fees and
  the fees embedded in purchases/sales, per year, per month and per
  instrument.

Amounts are reported in their own currency *and*, when a dated reference
rate is known, converted into the portfolio's base currency with that
rate's provenance; a missing rate leaves the base amount `None` and lists
the currency — never a fabricated conversion (specs/PRODUCT_SPEC.md). A sale
whose lots were bought in another currency than the sale itself has no
meaningful P&L in one currency: it is flagged `mixed_currency` and excluded
from the totals rather than mixed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.fx import convert, prepare_fx
from app.domain.positions import (
    LOT_AFFECTING_TYPES,
    SaleMatch,
    quantize_money,
    replay_lots,
    to_decimal,
)
from app.models import Instrument, Portfolio, Transaction

INCOME_TYPES = ("dividende", "coupon", "interet")
FEE_TYPES = ("frais",)


@dataclass
class RealizedSale:
    transaction_id: str
    instrument_id: str
    symbol: str
    name: str
    trade_date: datetime
    quantity: Decimal
    unit_price: Decimal
    currency: str
    proceeds: Decimal  # quantity × price − fees
    cost_basis: Decimal | None  # Σ consumed quantity × lot unit cost (lot currency)
    realized_pnl: Decimal | None
    realized_pnl_base: Decimal | None
    holding_days: int | None  # from the oldest consumed lot
    mixed_currency: bool
    fx_rate: Decimal | None = None
    fx_source: str | None = None


@dataclass
class RealizedTotal:
    key: str  # a year ("2025") or an instrument id
    label: str
    sales: int
    realized_pnl_base: Decimal
    gains_base: Decimal
    losses_base: Decimal


@dataclass
class RealizedReport:
    base_currency: str
    sales: list[RealizedSale]
    by_year: list[RealizedTotal]
    by_instrument: list[RealizedTotal]
    total_realized_pnl_base: Decimal
    unconverted_currencies: list[str]
    mixed_currency_sales: int
    method: str = (
        "appariement FIFO des ventes aux lots d'achat (frais d'achat inclus dans le coût, frais de vente "
        "déduits du produit) ; conversion au taux de référence daté du jour de la vente"
    )


def _sale_rows(db: Session, portfolio: Portfolio) -> list[tuple[Instrument, SaleMatch]]:
    instrument_ids = set(
        db.scalars(
            select(Transaction.instrument_id).where(
                Transaction.portfolio_id == portfolio.id,
                Transaction.reversed_at.is_(None),
                Transaction.type == "vente",
            )
        )
    )
    rows: list[tuple[Instrument, SaleMatch]] = []
    for instrument_id in sorted(i for i in instrument_ids if i):
        instrument = db.get(Instrument, instrument_id)
        if instrument is None:
            continue
        transactions = list(
            db.scalars(
                select(Transaction)
                .where(
                    Transaction.portfolio_id == portfolio.id,
                    Transaction.instrument_id == instrument_id,
                    Transaction.reversed_at.is_(None),
                    Transaction.type.in_(LOT_AFFECTING_TYPES),
                )
                .order_by(Transaction.trade_date, Transaction.created_at)
            )
        )
        sales: list[SaleMatch] = []
        try:
            replay_lots(transactions, sales)
        except ValueError:
            # An oversold history (only possible through data older than the
            # oversell guard) cannot be matched: report nothing for this
            # instrument rather than a partial, misleading figure.
            continue
        rows.extend((instrument, match) for match in sales)
    return rows


def realized_report(db: Session, portfolio: Portfolio, year: int | None = None) -> RealizedReport:
    rows = _sale_rows(db, portfolio)
    if year is not None:
        rows = [(i, m) for i, m in rows if m.transaction.trade_date.year == year]
    currencies = {m.transaction.currency for _, m in rows}
    if rows:
        dates = [m.transaction.trade_date for _, m in rows]
        prepare_fx(db, currencies, portfolio.base_currency, min(dates), max(dates))

    sales: list[RealizedSale] = []
    unconverted: set[str] = set()
    for instrument, match in rows:
        tx = match.transaction
        quantity = to_decimal(tx.quantity)
        unit_price = to_decimal(tx.unit_price)
        fees = to_decimal(tx.fees or 0)
        proceeds = quantize_money(quantity * unit_price - fees)
        lot_currencies = {c.currency for c in match.consumptions}
        mixed = bool(lot_currencies - {tx.currency})
        cost_basis = None
        pnl = None
        pnl_base = None
        fx_rate = fx_source = None
        if not mixed:
            cost_basis = quantize_money(sum((c.quantity * c.unit_cost for c in match.consumptions), Decimal("0")))
            pnl = quantize_money(proceeds - cost_basis)
            conversion = convert(db, pnl, tx.currency, portfolio.base_currency, tx.trade_date)
            if conversion is None:
                unconverted.add(tx.currency)
            else:
                pnl_base = conversion.amount
                fx_rate, fx_source = conversion.rate, conversion.source
        oldest = min((c.opened_at for c in match.consumptions), default=None)
        sales.append(
            RealizedSale(
                transaction_id=tx.id,
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                name=instrument.name,
                trade_date=tx.trade_date,
                quantity=quantity,
                unit_price=unit_price,
                currency=tx.currency,
                proceeds=proceeds,
                cost_basis=cost_basis,
                realized_pnl=pnl,
                realized_pnl_base=pnl_base,
                holding_days=(tx.trade_date - oldest).days if oldest else None,
                mixed_currency=mixed,
                fx_rate=fx_rate,
                fx_source=fx_source,
            )
        )
    sales.sort(key=lambda s: (s.trade_date, s.symbol))

    def _totals(key_of, label_of) -> list[RealizedTotal]:
        acc: dict[str, RealizedTotal] = {}
        for s in sales:
            if s.realized_pnl_base is None:
                continue
            key = key_of(s)
            total = acc.setdefault(key, RealizedTotal(key, label_of(s), 0, Decimal("0"), Decimal("0"), Decimal("0")))
            total.sales += 1
            total.realized_pnl_base += s.realized_pnl_base
            if s.realized_pnl_base >= 0:
                total.gains_base += s.realized_pnl_base
            else:
                total.losses_base += s.realized_pnl_base
        return sorted(acc.values(), key=lambda t: t.key)

    by_year = _totals(lambda s: str(s.trade_date.year), lambda s: str(s.trade_date.year))
    by_instrument = _totals(lambda s: s.instrument_id, lambda s: s.symbol)
    return RealizedReport(
        base_currency=portfolio.base_currency,
        sales=sales,
        by_year=by_year,
        by_instrument=sorted(by_instrument, key=lambda t: t.label),
        total_realized_pnl_base=quantize_money(sum((t.realized_pnl_base for t in by_year), Decimal("0"))),
        unconverted_currencies=sorted(unconverted),
        mixed_currency_sales=sum(1 for s in sales if s.mixed_currency),
    )


@dataclass
class IncomeRow:
    transaction_id: str
    trade_date: datetime
    type: str  # dividende | coupon | interet | frais | frais_transaction
    instrument_id: str | None
    symbol: str | None
    amount: Decimal  # signed: income positive, fees negative
    currency: str
    amount_base: Decimal | None
    note: str | None


@dataclass
class IncomeTotal:
    key: str
    label: str
    income_base: Decimal = Decimal("0")
    fees_base: Decimal = Decimal("0")
    count: int = 0

    @property
    def net_base(self) -> Decimal:
        return self.income_base + self.fees_base


@dataclass
class IncomeReport:
    base_currency: str
    rows: list[IncomeRow]
    by_year: list[IncomeTotal]
    by_month: list[IncomeTotal]
    by_instrument: list[IncomeTotal]
    total_income_base: Decimal
    total_fees_base: Decimal
    unconverted_currencies: list[str] = field(default_factory=list)
    method: str = (
        "dividendes, coupons et intérêts encaissés (montants nets tels que saisis) ; frais autonomes et frais "
        "inclus dans les achats/ventes, comptés négativement ; conversion au taux daté de chaque opération"
    )


def income_report(db: Session, portfolio: Portfolio, year: int | None = None) -> IncomeReport:
    query = select(Transaction).where(
        Transaction.portfolio_id == portfolio.id,
        Transaction.reversed_at.is_(None),
        Transaction.type.in_(INCOME_TYPES + FEE_TYPES + ("achat", "vente")),
    )
    transactions = [t for t in db.scalars(query.order_by(Transaction.trade_date, Transaction.created_at))]
    if year is not None:
        transactions = [t for t in transactions if t.trade_date.year == year]

    candidates: list[tuple[Transaction, str, Decimal]] = []
    for tx in transactions:
        if tx.type in INCOME_TYPES:
            candidates.append((tx, tx.type, to_decimal(tx.unit_price) - to_decimal(tx.fees or 0)))
        elif tx.type in FEE_TYPES:
            candidates.append((tx, tx.type, -(to_decimal(tx.unit_price) + to_decimal(tx.fees or 0))))
        elif to_decimal(tx.fees or 0) != 0:
            candidates.append((tx, "frais_transaction", -to_decimal(tx.fees)))

    currencies = {tx.currency for tx, _, _ in candidates}
    if candidates:
        dates = [tx.trade_date for tx, _, _ in candidates]
        prepare_fx(db, currencies, portfolio.base_currency, min(dates), max(dates))

    rows: list[IncomeRow] = []
    unconverted: set[str] = set()
    for tx, kind, amount in candidates:
        amount = quantize_money(amount)
        conversion = convert(db, amount, tx.currency, portfolio.base_currency, tx.trade_date)
        if conversion is None:
            unconverted.add(tx.currency)
        instrument = tx.instrument
        rows.append(
            IncomeRow(
                transaction_id=tx.id,
                trade_date=tx.trade_date,
                type=kind,
                instrument_id=instrument.id if instrument else None,
                symbol=instrument.symbol if instrument else None,
                amount=amount,
                currency=tx.currency,
                amount_base=conversion.amount if conversion else None,
                note=tx.note,
            )
        )

    def _totals(key_of, label_of) -> list[IncomeTotal]:
        acc: dict[str, IncomeTotal] = {}
        for r in rows:
            if r.amount_base is None:
                continue
            key = key_of(r)
            if key is None:
                continue
            total = acc.setdefault(key, IncomeTotal(key, label_of(r)))
            total.count += 1
            if r.amount_base >= 0:
                total.income_base += r.amount_base
            else:
                total.fees_base += r.amount_base
        return sorted(acc.values(), key=lambda t: t.key)

    by_year = _totals(lambda r: str(r.trade_date.year), lambda r: str(r.trade_date.year))
    by_month = _totals(lambda r: r.trade_date.strftime("%Y-%m"), lambda r: r.trade_date.strftime("%Y-%m"))
    by_instrument = sorted(_totals(lambda r: r.instrument_id, lambda r: r.symbol or ""), key=lambda t: t.label)
    return IncomeReport(
        base_currency=portfolio.base_currency,
        rows=rows,
        by_year=by_year,
        by_month=by_month,
        by_instrument=by_instrument,
        total_income_base=quantize_money(sum((t.income_base for t in by_year), Decimal("0"))),
        total_fees_base=quantize_money(sum((t.fees_base for t in by_year), Decimal("0"))),
        unconverted_currencies=sorted(unconverted),
    )
