"""Historical valuation, allocation, risk, performance (TWR/MWR) and
technical indicators — specs/ANALYTICS_AND_CHARTS.md.

Every figure here is descriptive of the past, never a recommendation
(specs/UX_SPEC.md, specs/PREDICTION.md's spirit applied to V1 analytics too).
Coverage is always disclosed: fewer than two data points means a metric
cannot be computed, and the response says so explicitly rather than
returning a misleading number - the same "never invented, always flagged"
principle used throughout app/domain/positions.py.

`compute_positions`/`compute_valuation` (app/domain/positions.py) read the
materialized `PositionLot` table, which only ever reflects *now*. Historical
("as of a past date") valuation needs a different query - replay each
instrument's transactions up to that date directly - so this module has its
own `*_as_of` functions rather than bolting an `as_of` parameter onto the
already-shipped, PositionLot-backed ones.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.positions import (
    LOT_AFFECTING_TYPES,
    PositionView,
    ValuationView,
    cash_delta,
    freshness_status,
    quantize_money,
    replay_lots,
    to_decimal,
)
from app.models import Instrument, Portfolio, PricePoint, Transaction

_EPSILON = timedelta(microseconds=1)


def _instrument_transactions_as_of(
    db: Session, portfolio_id: str, instrument_id: str, as_of: datetime
) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.instrument_id == instrument_id,
                Transaction.reversed_at.is_(None),
                Transaction.type.in_(LOT_AFFECTING_TYPES),
                Transaction.trade_date <= as_of,
            )
            .order_by(Transaction.trade_date, Transaction.created_at)
        )
    )


def _price_as_of(db: Session, instrument_id: str, as_of: datetime) -> PricePoint | None:
    return db.scalars(
        select(PricePoint)
        .where(PricePoint.instrument_id == instrument_id, PricePoint.as_of <= as_of)
        .order_by(PricePoint.as_of.desc())
        .limit(1)
    ).first()


def compute_positions_as_of(db: Session, portfolio: Portfolio, as_of: datetime) -> list[PositionView]:
    instrument_ids = set(
        db.scalars(
            select(Transaction.instrument_id).where(
                Transaction.portfolio_id == portfolio.id,
                Transaction.reversed_at.is_(None),
                Transaction.instrument_id.is_not(None),
                Transaction.trade_date <= as_of,
                Transaction.type.in_(LOT_AFFECTING_TYPES),
            )
        )
    )
    views: list[PositionView] = []
    for instrument_id in instrument_ids:
        instrument = db.get(Instrument, instrument_id)
        if instrument is None:
            continue
        lots = replay_lots(_instrument_transactions_as_of(db, portfolio.id, instrument_id, as_of))
        total_quantity = sum((to_decimal(lot.quantity_remaining) for lot in lots), Decimal("0"))
        if total_quantity <= 0:
            continue
        total_cost = sum((to_decimal(lot.quantity_remaining) * to_decimal(lot.unit_cost) for lot in lots), Decimal("0"))
        average_unit_cost = quantize_money(total_cost / total_quantity)
        price = _price_as_of(db, instrument_id, as_of)
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


def cash_balance_by_currency_as_of(db: Session, portfolio_id: str, as_of: datetime) -> dict[str, Decimal]:
    transactions = db.scalars(
        select(Transaction).where(
            Transaction.portfolio_id == portfolio_id,
            Transaction.reversed_at.is_(None),
            Transaction.trade_date <= as_of,
        )
    )
    balances: dict[str, Decimal] = {}
    for tx in transactions:
        balances[tx.currency] = balances.get(tx.currency, Decimal("0")) + cash_delta(tx)
    return balances


def compute_valuation_as_of(db: Session, portfolio: Portfolio, as_of: datetime) -> ValuationView:
    positions = compute_positions_as_of(db, portfolio, as_of)
    cash_by_currency = cash_balance_by_currency_as_of(db, portfolio.id, as_of)

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


@dataclass
class ValuationPoint:
    as_of: datetime
    cash: Decimal
    positions_value: Decimal
    total_value: Decimal
    has_missing_prices: bool


def _candidate_dates(db: Session, portfolio_id: str, start: datetime, end: datetime) -> list[datetime]:
    """Real dates only - specs/ANALYTICS_AND_CHARTS.md: no fake daily
    precision. The union of every transaction and price date in range, plus
    the range's own boundaries so the series always covers what was asked."""
    dates = set(
        db.scalars(
            select(Transaction.trade_date).where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.reversed_at.is_(None),
                Transaction.trade_date >= start,
                Transaction.trade_date <= end,
            )
        )
    )
    instrument_ids = list(
        db.scalars(
            select(Transaction.instrument_id)
            .where(Transaction.portfolio_id == portfolio_id, Transaction.instrument_id.is_not(None))
            .distinct()
        )
    )
    if instrument_ids:
        dates.update(
            db.scalars(
                select(PricePoint.as_of).where(
                    PricePoint.instrument_id.in_(instrument_ids),
                    PricePoint.as_of >= start,
                    PricePoint.as_of <= end,
                )
            )
        )
    dates.add(start)
    dates.add(end)
    return sorted(d for d in dates if start <= d <= end)


def valuation_history(db: Session, portfolio: Portfolio, start: datetime, end: datetime) -> list[ValuationPoint]:
    points = []
    for as_of in _candidate_dates(db, portfolio.id, start, end):
        valuation = compute_valuation_as_of(db, portfolio, as_of)
        points.append(
            ValuationPoint(
                as_of=as_of,
                cash=valuation.cash,
                positions_value=valuation.positions_value,
                total_value=valuation.total_value,
                has_missing_prices=valuation.has_missing_prices,
            )
        )
    return points


@dataclass
class AllocationSlice:
    label: str
    value: Decimal
    share: Decimal  # 0-1, of the base-currency total only (see ValuationView.unconverted_currencies)


@dataclass
class AllocationView:
    base_currency: str
    total_value: Decimal
    by_asset_class: list[AllocationSlice]
    by_instrument: list[AllocationSlice]
    by_currency: list[AllocationSlice]
    unconverted_currencies: list[str]


def _slices(amounts: dict[str, Decimal], total: Decimal) -> list[AllocationSlice]:
    if total <= 0:
        return [AllocationSlice(label=label, value=value, share=Decimal("0")) for label, value in amounts.items()]
    return [
        AllocationSlice(label=label, value=value, share=(value / total).quantize(Decimal("0.0001")))
        for label, value in amounts.items()
    ]


def allocation_breakdown(db: Session, portfolio: Portfolio, positions: list[PositionView]) -> AllocationView:
    """Invested positions only - cash is deliberately not a slice here. It is
    already its own dashboard element (specs/UX_SPEC.md: "Cartes valeur
    totale, variation, cash, allocation" lists it separately from
    allocation), and folding it in would make "100% cash, no positions yet"
    render as an empty chart instead of a clear, separate cash figure."""
    by_class: dict[str, Decimal] = {}
    by_instrument: dict[str, Decimal] = {}
    by_currency: dict[str, Decimal] = {}
    unconverted: set[str] = set()
    base_total = Decimal("0")

    for position in positions:
        if position.market_value is None or not position.matches_base_currency:
            if not position.matches_base_currency:
                unconverted.add(position.currency)
            continue
        by_class[position.instrument.asset_class] = (
            by_class.get(position.instrument.asset_class, Decimal("0")) + position.market_value
        )
        by_instrument[position.instrument.symbol] = (
            by_instrument.get(position.instrument.symbol, Decimal("0")) + position.market_value
        )
        by_currency[position.currency] = by_currency.get(position.currency, Decimal("0")) + position.market_value
        base_total += position.market_value

    return AllocationView(
        base_currency=portfolio.base_currency,
        total_value=base_total,
        by_asset_class=_slices(by_class, base_total),
        by_instrument=_slices(by_instrument, base_total),
        by_currency=_slices(by_currency, base_total),
        unconverted_currencies=sorted(unconverted),
    )


@dataclass
class RiskView:
    has_sufficient_data: bool
    volatility_annualized: Decimal | None
    max_drawdown: Decimal | None
    observations: int
    method: str


def risk_metrics(history: list[ValuationPoint]) -> RiskView:
    """Volatility (stdev of period returns, annualized by the *average*
    sampling interval - our snapshots are irregular, unlike a daily price
    feed) and maximum drawdown. Both are purely descriptive - see module
    docstring."""
    method = (
        "Écart-type des rendements entre points de valorisation successifs, annualisé par "
        "l'intervalle moyen observé (échantillonnage irrégulier - approximation) ; "
        "repli maximal = pire baisse pic-creux sur la période."
    )
    values = [p.total_value for p in history if p.total_value > 0]
    if len(values) < 3:
        return RiskView(
            has_sufficient_data=False,
            volatility_annualized=None,
            max_drawdown=None,
            observations=len(values),
            method=method,
        )

    returns = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]
    float_returns = [float(r) for r in returns]
    stdev = statistics.stdev(float_returns)

    span_days = (history[-1].as_of - history[0].as_of).days or 1
    periods_per_year = max(len(returns) / (span_days / 365.0), 1e-9)
    volatility_annualized = Decimal(str(stdev * (periods_per_year**0.5))).quantize(Decimal("0.0001"))

    peak = values[0]
    max_dd = Decimal("0")
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            drawdown = (v - peak) / peak
            max_dd = min(max_dd, drawdown)

    return RiskView(
        has_sufficient_data=True,
        volatility_annualized=volatility_annualized,
        max_drawdown=max_dd.quantize(Decimal("0.0001")),
        observations=len(values),
        method=method,
    )


def xnpv(rate: Decimal, flows: list[tuple[datetime, Decimal]]) -> Decimal:
    t0 = flows[0][0]
    total = Decimal("0")
    for t, cf in flows:
        days = Decimal((t - t0).days)
        total += cf / (Decimal(1) + rate) ** (days / Decimal(365))
    return total


def xirr(flows: list[tuple[datetime, Decimal]]) -> Decimal | None:
    """Bisection - simple and dependency-free rather than Newton's method,
    which needs a derivative. Returns None if no root is bracketed in
    [-99.99%, 1000%] (e.g. all cash flows have the same sign)."""
    if len(flows) < 2:
        return None
    low, high = Decimal("-0.9999"), Decimal("10")
    f_low, f_high = xnpv(low, flows), xnpv(high, flows)
    if f_low == 0:
        return low
    if f_high == 0:
        return high
    if (f_low > 0) == (f_high > 0):
        return None
    mid = low
    for _ in range(100):
        mid = (low + high) / 2
        f_mid = xnpv(mid, flows)
        if abs(f_mid) < Decimal("0.0001"):
            return mid
        if (f_mid > 0) == (f_low > 0):
            low, f_low = mid, f_mid
        else:
            high = mid
    return mid


@dataclass
class PerformanceView:
    has_sufficient_data: bool
    start: datetime
    end: datetime
    base_currency: str
    twr: Decimal | None
    mwr: Decimal | None
    external_flow_count: int
    method: str


_PERFORMANCE_METHOD = (
    "TWR (rendement pondéré dans le temps) : rendements chaînés entre chaque dépôt/retrait externe, "
    "annulant l'effet de leur montant sur la performance mesurée. MWR (rendement pondéré par l'argent) : "
    "taux de rendement interne (IRR) sur les mêmes flux. Dividendes/coupons restent en trésorerie "
    "interne, non traités comme des flux externes. N'inclut pas de comparaison à un indice."
)


def performance(db: Session, portfolio: Portfolio, start: datetime, end: datetime) -> PerformanceView:
    external_flows = list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.portfolio_id == portfolio.id,
                Transaction.reversed_at.is_(None),
                Transaction.type.in_(("depot", "retrait")),
                Transaction.trade_date > start,
                Transaction.trade_date <= end,
            )
            .order_by(Transaction.trade_date, Transaction.created_at)
        )
    )

    v_start = compute_valuation_as_of(db, portfolio, start).total_value
    v_end = compute_valuation_as_of(db, portfolio, end).total_value

    cumulative = Decimal(1)
    v_after_prev = v_start
    xirr_flows: list[tuple[datetime, Decimal]] = [(start, -v_start)]
    any_period = False
    for tx in external_flows:
        v_before = compute_valuation_as_of(db, portfolio, tx.trade_date - _EPSILON).total_value
        if v_after_prev > 0:
            cumulative *= 1 + (v_before - v_after_prev) / v_after_prev
            any_period = True
        v_after_prev = compute_valuation_as_of(db, portfolio, tx.trade_date).total_value
        xirr_flows.append((tx.trade_date, -cash_delta(tx)))
    if v_after_prev > 0:
        cumulative *= 1 + (v_end - v_after_prev) / v_after_prev
        any_period = True
    xirr_flows.append((end, v_end))

    twr = (cumulative - 1).quantize(Decimal("0.0001")) if any_period else None
    mwr = xirr(xirr_flows)
    if mwr is not None:
        mwr = mwr.quantize(Decimal("0.0001"))

    return PerformanceView(
        has_sufficient_data=any_period,
        start=start,
        end=end,
        base_currency=portfolio.base_currency,
        twr=twr,
        mwr=mwr,
        external_flow_count=len(external_flows),
        method=_PERFORMANCE_METHOD,
    )


# --- Technical indicators (pure functions - no DB) ---


@dataclass
class IndicatorSeries:
    dates: list[datetime]
    prices: list[Decimal]
    sma: list[Decimal | None]
    ema: list[Decimal | None]
    rsi: list[Decimal | None]
    macd: list[Decimal | None]
    macd_signal: list[Decimal | None]


def _sma(values: list[Decimal], window: int) -> list[Decimal | None]:
    result: list[Decimal | None] = []
    for i in range(len(values)):
        if i + 1 < window:
            result.append(None)
        else:
            window_slice = values[i + 1 - window : i + 1]
            result.append((sum(window_slice, Decimal("0")) / window).quantize(Decimal("0.000001")))
    return result


def _ema_series(values: list[Decimal], window: int) -> list[Decimal | None]:
    result: list[Decimal | None] = []
    multiplier = Decimal(2) / (window + 1)
    ema_prev: Decimal | None = None
    for i, value in enumerate(values):
        if i + 1 < window:
            result.append(None)
            continue
        if ema_prev is None:
            ema_prev = sum(values[i + 1 - window : i + 1], Decimal("0")) / window
        else:
            ema_prev = (value - ema_prev) * multiplier + ema_prev
        result.append(ema_prev.quantize(Decimal("0.000001")))
    return result


def _rsi(values: list[Decimal], window: int) -> list[Decimal | None]:
    result: list[Decimal | None] = [None]
    gains = []
    losses = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, Decimal("0")))
        losses.append(max(-delta, Decimal("0")))
        if i < window:
            result.append(None)
            continue
        avg_gain = sum(gains[-window:], Decimal("0")) / window
        avg_loss = sum(losses[-window:], Decimal("0")) / window
        if avg_loss == 0:
            result.append(Decimal("100"))
        else:
            rs = avg_gain / avg_loss
            rsi = Decimal(100) - (Decimal(100) / (1 + rs))
            result.append(rsi.quantize(Decimal("0.01")))
    return result


def compute_indicators(
    dates: list[datetime],
    prices: list[Decimal],
    sma_window: int = 20,
    ema_window: int = 12,
    rsi_window: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal_window: int = 9,
) -> IndicatorSeries:
    """SMA/EMA/RSI/MACD over an arbitrary (possibly sparse, possibly
    irregularly-spaced) price series - specs/ANALYTICS_AND_CHARTS.md:
    "Indicateurs : SMA/EMA/RSI/MACD, avec paramètres visibles et aucune
    alerte prescriptive". `None` wherever a window hasn't filled yet, never a
    fabricated early value."""
    sma = _sma(prices, sma_window)
    ema = _ema_series(prices, ema_window)
    rsi = _rsi(prices, rsi_window)

    ema_fast = _ema_series(prices, macd_fast)
    ema_slow = _ema_series(prices, macd_slow)
    macd_line: list[Decimal | None] = [
        (f - s) if f is not None and s is not None else None for f, s in zip(ema_fast, ema_slow, strict=True)
    ]
    macd_values = [m for m in macd_line if m is not None]
    signal_partial = _ema_series(macd_values, macd_signal_window) if macd_values else []
    macd_signal: list[Decimal | None] = []
    signal_iter = iter(signal_partial)
    for m in macd_line:
        macd_signal.append(next(signal_iter) if m is not None else None)

    return IndicatorSeries(
        dates=dates,
        prices=prices,
        sma=sma,
        ema=ema,
        rsi=rsi,
        macd=macd_line,
        macd_signal=macd_signal,
    )
