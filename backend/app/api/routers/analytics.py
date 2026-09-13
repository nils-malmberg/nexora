"""specs/ANALYTICS_AND_CHARTS.md — historical valuation, allocation, risk,
performance and the quantitative toolbox (return statistics, drawdown,
VaR/CVaR, CAPM, correlation, Markowitz frontier, Monte Carlo) for one
portfolio or one instrument. All figures describe the past or simulate
stated assumptions; coverage is disclosed and nothing is a recommendation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_owned_portfolio, get_visible_instrument
from app.domain import quant
from app.domain.analytics import allocation_breakdown, performance, risk_metrics, valuation_history
from app.domain.positions import compute_positions
from app.market import service as market_service
from app.models import Instrument, OhlcBar, Portfolio, PricePoint, Transaction, User
from app.observability.metrics import analytics_requests_total
from app.schemas.analytics import (
    AllocationOut,
    AllocationSliceOut,
    HistoryOut,
    PerformanceOut,
    RiskOut,
    ValuationPointOut,
)
from app.schemas.quant import (
    CapmOut,
    CorrelationOut,
    DrawdownOut,
    DrawdownPointOut,
    FrontierOut,
    FrontierPointOut,
    MonteCarloOut,
    ReturnStatsOut,
    VarOut,
)

router = APIRouter(prefix="/api/v1", tags=["analytics"])

FRONTIER_DISCLAIMER = (
    "Frontière efficiente calculée sur des rendements passés : les espérances et covariances "
    "estimées sont instables et ne prédisent pas l'avenir. Outil pédagogique, pas une allocation recommandée."
)
MC_DISCLAIMER = (
    "Simulation sous hypothèse de mouvement brownien géométrique (rendements normaux et indépendants), "
    "calibrée sur le passé : une illustration de la dispersion possible, pas une prévision."
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _default_start(db: Session, portfolio_id: str) -> datetime:
    earliest = db.scalars(
        select(Transaction.trade_date)
        .where(Transaction.portfolio_id == portfolio_id, Transaction.reversed_at.is_(None))
        .order_by(Transaction.trade_date)
        .limit(1)
    ).first()
    return earliest or datetime.now(UTC)


def _resolve_range(
    db: Session, portfolio_id: str, start: datetime | None, end: datetime | None
) -> tuple[datetime, datetime]:
    return start or _default_start(db, portfolio_id), end or datetime.now(UTC)


def _instrument_series(db: Session, instrument: Instrument, days: int) -> list[tuple[datetime, float]]:
    """Daily closes (topping up the cache for catalog instruments), else one
    price point per day."""
    now = datetime.now(UTC)
    start = now - timedelta(days=days)
    if instrument.user_id is None and instrument.provider not in (None, "manual", "null"):
        market_service.get_history(db, instrument, start, now)
    bars = db.scalars(
        select(OhlcBar).where(OhlcBar.instrument_id == instrument.id, OhlcBar.as_of >= start).order_by(OhlcBar.as_of)
    ).all()
    if bars:
        return [(b.as_of.date(), float(b.close)) for b in bars]
    by_day: dict = {}
    for p in db.scalars(
        select(PricePoint)
        .where(PricePoint.instrument_id == instrument.id, PricePoint.as_of >= start)
        .order_by(PricePoint.as_of)
    ):
        by_day[p.as_of.date()] = float(p.price)
    return sorted(by_day.items())


def _portfolio_series(db: Session, portfolio: Portfolio, start: datetime, end: datetime) -> list[tuple]:
    """Portfolio value on real dates, starting no earlier than its first
    transaction: the empty pre-history (value 0 every day) is not a return
    series, and would turn the first purchase into an infinite return."""
    start = max(start, _default_start(db, portfolio.id))
    return [(p.as_of.date(), float(p.total_value)) for p in valuation_history(db, portfolio, start, end)]


def _subject_series(
    db: Session, user: User, portfolio_id: str | None, instrument_id: str | None, days: int
) -> tuple[str, str, str | None, list[tuple]]:
    """Resolves the `portfolio_id` / `instrument_id` query params into a
    (subject key, label, currency, [(date, value)]) tuple."""
    if instrument_id:
        instrument = get_visible_instrument(instrument_id, db, user)
        return (
            f"instrument:{instrument.id}",
            instrument.symbol,
            instrument.currency,
            _instrument_series(db, instrument, days),
        )
    if portfolio_id:
        portfolio = get_owned_portfolio(portfolio_id, db, user)
        end = datetime.now(UTC)
        return (
            f"portfolio:{portfolio.id}",
            portfolio.name,
            portfolio.base_currency,
            _portfolio_series(db, portfolio, end - timedelta(days=days), end),
        )
    raise HTTPException(status_code=422, detail="portfolio_id or instrument_id is required")


# ---------------------------------------------------------------------------
# Portfolio analytics (Phase 2)
# ---------------------------------------------------------------------------


@router.get("/portfolios/{portfolio_id}/analytics/history", response_model=HistoryOut)
def get_history(
    portfolio_id: str,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HistoryOut:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    analytics_requests_total.labels(endpoint="history").inc()
    range_start, range_end = _resolve_range(db, portfolio.id, start, end)
    points = valuation_history(db, portfolio, range_start, range_end)
    return HistoryOut(
        base_currency=portfolio.base_currency,
        points=[
            ValuationPointOut(
                as_of=p.as_of,
                cash=p.cash,
                positions_value=p.positions_value,
                total_value=p.total_value,
                has_missing_prices=p.has_missing_prices,
            )
            for p in points
        ],
    )


@router.get("/portfolios/{portfolio_id}/analytics/allocation", response_model=AllocationOut)
def get_allocation(
    portfolio_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> AllocationOut:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    analytics_requests_total.labels(endpoint="allocation").inc()
    positions = compute_positions(db, portfolio)
    allocation = allocation_breakdown(db, portfolio, positions)
    return AllocationOut(
        base_currency=allocation.base_currency,
        total_value=allocation.total_value,
        by_asset_class=[
            AllocationSliceOut(label=s.label, value=s.value, share=s.share) for s in allocation.by_asset_class
        ],
        by_instrument=[
            AllocationSliceOut(label=s.label, value=s.value, share=s.share) for s in allocation.by_instrument
        ],
        by_currency=[AllocationSliceOut(label=s.label, value=s.value, share=s.share) for s in allocation.by_currency],
        unconverted_currencies=allocation.unconverted_currencies,
    )


@router.get("/portfolios/{portfolio_id}/analytics/risk", response_model=RiskOut)
def get_risk(
    portfolio_id: str,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RiskOut:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    analytics_requests_total.labels(endpoint="risk").inc()
    range_start, range_end = _resolve_range(db, portfolio.id, start, end)
    risk = risk_metrics(valuation_history(db, portfolio, range_start, range_end))
    return RiskOut(
        has_sufficient_data=risk.has_sufficient_data,
        volatility_annualized=risk.volatility_annualized,
        max_drawdown=risk.max_drawdown,
        observations=risk.observations,
        method=risk.method,
    )


@router.get("/portfolios/{portfolio_id}/analytics/performance", response_model=PerformanceOut)
def get_performance(
    portfolio_id: str,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PerformanceOut:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    analytics_requests_total.labels(endpoint="performance").inc()
    range_start, range_end = _resolve_range(db, portfolio.id, start, end)
    perf = performance(db, portfolio, range_start, range_end)
    return PerformanceOut(
        has_sufficient_data=perf.has_sufficient_data,
        start=perf.start,
        end=perf.end,
        base_currency=perf.base_currency,
        twr=perf.twr,
        mwr=perf.mwr,
        external_flow_count=perf.external_flow_count,
        method=perf.method,
    )


# ---------------------------------------------------------------------------
# Quant toolbox (portfolio or instrument)
# ---------------------------------------------------------------------------


@router.get("/quant/stats", response_model=ReturnStatsOut)
def get_return_stats(
    portfolio_id: str | None = None,
    instrument_id: str | None = None,
    days: int = Query(default=365, ge=30, le=3660),
    risk_free_rate: float = Query(default=0.0, ge=-0.05, le=0.2),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReturnStatsOut:
    analytics_requests_total.labels(endpoint="quant_stats").inc()
    subject, label, currency, series = _subject_series(db, user, portfolio_id, instrument_id, days)
    stats = quant.return_stats([v for _, v in series], risk_free_rate=risk_free_rate)
    return ReturnStatsOut(
        subject=subject,
        label=label,
        currency=currency,
        start=datetime.combine(series[0][0], datetime.min.time(), tzinfo=UTC) if series else None,
        end=datetime.combine(series[-1][0], datetime.min.time(), tzinfo=UTC) if series else None,
        **stats.__dict__,
    )


@router.get("/quant/drawdown", response_model=DrawdownOut)
def get_drawdown(
    portfolio_id: str | None = None,
    instrument_id: str | None = None,
    days: int = Query(default=365, ge=30, le=3660),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DrawdownOut:
    analytics_requests_total.labels(endpoint="quant_drawdown").inc()
    subject, _, _, series = _subject_series(db, user, portfolio_id, instrument_id, days)
    dd = quant.drawdown_series([v for _, v in series])
    points = [
        DrawdownPointOut(as_of=datetime.combine(d, datetime.min.time(), tzinfo=UTC), value=v, drawdown=x)
        for (d, v), x in zip(series, dd, strict=True)
    ]
    return DrawdownOut(subject=subject, points=points, max_drawdown=min(dd) if dd else None, observations=len(dd))


@router.get("/quant/var", response_model=VarOut)
def get_var(
    portfolio_id: str | None = None,
    instrument_id: str | None = None,
    days: int = Query(default=365, ge=60, le=3660),
    confidence: float = Query(default=0.95, ge=0.8, le=0.999),
    horizon: int = Query(default=1, ge=1, le=60),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VarOut:
    analytics_requests_total.labels(endpoint="quant_var").inc()
    subject, _, currency, series = _subject_series(db, user, portfolio_id, instrument_id, days)
    values = [v for _, v in series]
    var = quant.value_at_risk(values, confidence=confidence, horizon_periods=horizon)
    return VarOut(subject=subject, current_value=values[-1] if values else None, currency=currency, **var.__dict__)


@router.get("/quant/capm", response_model=CapmOut)
def get_capm(
    benchmark_instrument_id: str,
    portfolio_id: str | None = None,
    instrument_id: str | None = None,
    days: int = Query(default=365, ge=60, le=3660),
    risk_free_rate: float = Query(default=0.0, ge=-0.05, le=0.2),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CapmOut:
    analytics_requests_total.labels(endpoint="quant_capm").inc()
    subject, _, _, series = _subject_series(db, user, portfolio_id, instrument_id, days)
    benchmark = get_visible_instrument(benchmark_instrument_id, db, user)
    bench_series = _instrument_series(db, benchmark, days)
    _, aligned = quant.align_on_dates({"subject": series, "benchmark": bench_series})
    result = quant.capm(aligned.get("subject", []), aligned.get("benchmark", []), risk_free_rate=risk_free_rate)
    return CapmOut(subject=subject, benchmark=benchmark.symbol, risk_free_rate=risk_free_rate, **result.__dict__)


@router.get("/portfolios/{portfolio_id}/quant/correlation", response_model=CorrelationOut)
def get_correlation(
    portfolio_id: str,
    days: int = Query(default=365, ge=60, le=3660),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CorrelationOut:
    analytics_requests_total.labels(endpoint="quant_correlation").inc()
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    series = {p.instrument.symbol: _instrument_series(db, p.instrument, days) for p in compute_positions(db, portfolio)}
    series = {k: v for k, v in series.items() if len(v) >= 2}
    _, aligned = quant.align_on_dates(series)
    result = quant.correlation_matrix(aligned)
    return CorrelationOut(
        labels=result.labels,
        matrix=result.matrix,
        observations=result.observations,
        has_sufficient_data=result.has_sufficient_data,
    )


@router.get("/portfolios/{portfolio_id}/quant/frontier", response_model=FrontierOut)
def get_frontier(
    portfolio_id: str,
    days: int = Query(default=365, ge=90, le=3660),
    risk_free_rate: float = Query(default=0.0, ge=-0.05, le=0.2),
    points: int = Query(default=25, ge=5, le=60),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FrontierOut:
    analytics_requests_total.labels(endpoint="quant_frontier").inc()
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    positions = compute_positions(db, portfolio)
    series = {p.instrument.symbol: _instrument_series(db, p.instrument, days) for p in positions}
    series = {k: v for k, v in series.items() if len(v) >= 2}
    _, aligned = quant.align_on_dates(series)
    weights = None
    if aligned:
        by_symbol = {p.instrument.symbol: float(p.market_value_base or 0) for p in positions}
        weights = [by_symbol.get(k, 0.0) for k in aligned]
    result = quant.efficient_frontier(aligned, risk_free_rate=risk_free_rate, points=points, current_weights=weights)

    def pt(p):
        return FrontierPointOut(**p.__dict__) if p else None

    return FrontierOut(
        has_sufficient_data=result.has_sufficient_data,
        labels=result.labels,
        observations=result.observations,
        periods_per_year=result.periods_per_year,
        risk_free_rate=result.risk_free_rate,
        expected_returns=result.expected_returns,
        volatilities=result.volatilities,
        frontier=[pt(p) for p in result.frontier],
        min_variance=pt(result.min_variance),
        max_sharpe=pt(result.max_sharpe),
        equal_weight=pt(result.equal_weight),
        current=pt(result.current),
        method=result.method,
        disclaimer=FRONTIER_DISCLAIMER,
    )


@router.get("/quant/montecarlo", response_model=MonteCarloOut)
def get_monte_carlo(
    portfolio_id: str | None = None,
    instrument_id: str | None = None,
    days: int = Query(default=365, ge=60, le=3660),
    horizon: int = Query(default=252, ge=5, le=1260),
    simulations: int = Query(default=2000, ge=100, le=10000),
    seed: int = Query(default=42, ge=0, le=2**31 - 1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MonteCarloOut:
    analytics_requests_total.labels(endpoint="quant_montecarlo").inc()
    subject, _, currency, series = _subject_series(db, user, portfolio_id, instrument_id, days)
    values = [v for _, v in series]
    result = quant.monte_carlo_gbm(values, horizon_periods=horizon, simulations=simulations, seed=seed)
    return MonteCarloOut(
        subject=subject,
        start_value=values[-1] if values else None,
        currency=currency,
        disclaimer=MC_DISCLAIMER,
        **result.__dict__,
    )


__all__ = ["router", "Decimal"]
