"""Consolidated wealth across every portfolio of one user.

Someone who imports a Trade Republic export into one portfolio and a Revolut
export into another wants one number and one allocation. Each portfolio is
valued in its own base currency by the usual engine (app/domain/positions.py),
then converted into the user's reference currency with today's dated
reference rate; what cannot be converted is listed, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.analytics import AllocationSlice, _slices
from app.domain.fx import convert
from app.domain.positions import compute_positions, compute_valuation, quantize_money
from app.models import Portfolio, User


@dataclass
class ConsolidatedPortfolio:
    id: str
    name: str
    base_currency: str
    total_value: Decimal
    total_value_reference: Decimal | None
    cash_reference: Decimal | None
    positions: int
    has_missing_prices: bool
    unconverted_currencies: list[str]
    fx_rate: Decimal | None = None
    fx_source: str | None = None


@dataclass
class ConsolidatedView:
    reference_currency: str
    as_of: datetime
    total_value: Decimal
    cash: Decimal
    positions_value: Decimal
    portfolios: list[ConsolidatedPortfolio]
    by_portfolio: list[AllocationSlice]
    by_asset_class: list[AllocationSlice]
    by_instrument: list[AllocationSlice]
    by_currency: list[AllocationSlice]
    unconverted_currencies: list[str] = field(default_factory=list)
    has_missing_prices: bool = False


def consolidated_view(db: Session, user: User) -> ConsolidatedView:
    reference = user.reference_currency
    portfolios = db.scalars(select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.name)).all()

    cards: list[ConsolidatedPortfolio] = []
    by_portfolio: dict[str, Decimal] = {}
    by_class: dict[str, Decimal] = {}
    by_instrument: dict[str, Decimal] = {}
    by_currency: dict[str, Decimal] = {}
    unconverted: set[str] = set()
    total = cash_total = positions_total = Decimal("0")
    missing = False

    for portfolio in portfolios:
        positions = compute_positions(db, portfolio)
        valuation = compute_valuation(db, portfolio, positions)
        unconverted.update(valuation.unconverted_currencies)
        missing = missing or valuation.has_missing_prices
        conversion = convert(db, Decimal("1"), portfolio.base_currency, reference)
        rate = conversion.rate if conversion else None
        if rate is None:
            unconverted.add(portfolio.base_currency)
            cards.append(
                ConsolidatedPortfolio(
                    id=portfolio.id,
                    name=portfolio.name,
                    base_currency=portfolio.base_currency,
                    total_value=valuation.total_value,
                    total_value_reference=None,
                    cash_reference=None,
                    positions=len(positions),
                    has_missing_prices=valuation.has_missing_prices,
                    unconverted_currencies=valuation.unconverted_currencies,
                )
            )
            continue

        total_ref = quantize_money(valuation.total_value * rate)
        cash_ref = quantize_money(valuation.cash * rate)
        total += total_ref
        cash_total += cash_ref
        positions_total += quantize_money(valuation.positions_value * rate)
        by_portfolio[portfolio.name] = by_portfolio.get(portfolio.name, Decimal("0")) + total_ref
        if cash_ref:
            by_class["tresorerie"] = by_class.get("tresorerie", Decimal("0")) + cash_ref
            by_currency[portfolio.base_currency] = by_currency.get(portfolio.base_currency, Decimal("0")) + cash_ref
        for position in positions:
            value_base = position.market_value_base
            if value_base is None:
                continue
            value_ref = quantize_money(value_base * rate)
            cls = position.instrument.asset_class
            by_class[cls] = by_class.get(cls, Decimal("0")) + value_ref
            symbol = position.instrument.symbol
            by_instrument[symbol] = by_instrument.get(symbol, Decimal("0")) + value_ref
            by_currency[position.currency] = by_currency.get(position.currency, Decimal("0")) + value_ref
        cards.append(
            ConsolidatedPortfolio(
                id=portfolio.id,
                name=portfolio.name,
                base_currency=portfolio.base_currency,
                total_value=valuation.total_value,
                total_value_reference=total_ref,
                cash_reference=cash_ref,
                positions=len(positions),
                has_missing_prices=valuation.has_missing_prices,
                unconverted_currencies=valuation.unconverted_currencies,
                fx_rate=rate,
                fx_source=conversion.source if conversion else None,
            )
        )

    return ConsolidatedView(
        reference_currency=reference,
        as_of=datetime.now(UTC),
        total_value=quantize_money(total),
        cash=quantize_money(cash_total),
        positions_value=quantize_money(positions_total),
        portfolios=cards,
        by_portfolio=_slices(by_portfolio, total),
        by_asset_class=_slices(by_class, total),
        by_instrument=_slices(by_instrument, total),
        by_currency=_slices(by_currency, total),
        unconverted_currencies=sorted(unconverted),
        has_missing_prices=missing,
    )
