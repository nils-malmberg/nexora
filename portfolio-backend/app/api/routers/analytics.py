"""specs/ANALYTICS_AND_CHARTS.md — historical valuation, allocation, risk and
performance for one portfolio. All figures are descriptive of the past only;
see app/domain/analytics.py for coverage/disclosure rules."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_owned_portfolio
from app.domain.analytics import allocation_breakdown, performance, risk_metrics, valuation_history
from app.domain.positions import compute_positions
from app.models import Transaction, User
from app.observability.metrics import analytics_requests_total
from app.schemas.analytics import (
    AllocationOut,
    AllocationSliceOut,
    HistoryOut,
    PerformanceOut,
    RiskOut,
    ValuationPointOut,
)

router = APIRouter(prefix="/api/v1/portfolios/{portfolio_id}/analytics", tags=["analytics"])


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


@router.get("/history", response_model=HistoryOut)
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


@router.get("/allocation", response_model=AllocationOut)
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


@router.get("/risk", response_model=RiskOut)
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


@router.get("/performance", response_model=PerformanceOut)
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
