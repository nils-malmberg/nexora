"""Consolidated wealth, realized gains, income, strategy studies, rebased
comparison, informational alerts and notifications.

Registered *before* the portfolios router so `/portfolios/consolidated` is
not swallowed by `/portfolios/{portfolio_id}`. Everything here is read-only
analysis or an in-app note to the user — nothing is an order, a signal or a
recommendation (specs/PRODUCT_SPEC.md).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_owned_portfolio, get_visible_instrument, require_csrf
from app.api.routers.analytics import _instrument_series
from app.domain import quant
from app.domain.alerts import KIND_LABELS, evaluate_alerts
from app.domain.consolidated import consolidated_view
from app.domain.realized import income_report, realized_report
from app.models import AuditEvent, Notification, PriceAlert, User
from app.observability.metrics import analytics_requests_total
from app.schemas.analytics import AllocationSliceOut
from app.schemas.instruments import InstrumentOut
from app.schemas.quant import ReturnStatsOut
from app.schemas.wealth import (
    AlertCreate,
    AlertOut,
    CompareOut,
    CompareSeriesOut,
    ConsolidatedOut,
    ConsolidatedPortfolioOut,
    IncomeOut,
    IncomeRowOut,
    IncomeTotalOut,
    MarkReadRequest,
    NotificationOut,
    NotificationsOut,
    RealizedOut,
    RealizedSaleOut,
    RealizedTotalOut,
    StrategyStudyOut,
    StrategyTradeOut,
)

router = APIRouter(prefix="/api/v1", tags=["wealth"])

MAX_ALERTS_PER_USER = 200
MAX_COMPARE_INSTRUMENTS = 6


def _slices(slices) -> list[AllocationSliceOut]:
    return [AllocationSliceOut(label=s.label, value=s.value, share=s.share) for s in slices]


def _dt(d) -> datetime:
    return d if isinstance(d, datetime) else datetime.combine(d, datetime.min.time(), tzinfo=UTC)


# ---------------------------------------------------------------------------
# Consolidated wealth
# ---------------------------------------------------------------------------


@router.get("/portfolios/consolidated", response_model=ConsolidatedOut)
def get_consolidated(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ConsolidatedOut:
    analytics_requests_total.labels(endpoint="consolidated").inc()
    view = consolidated_view(db, user)
    return ConsolidatedOut(
        reference_currency=view.reference_currency,
        as_of=view.as_of,
        total_value=view.total_value,
        cash=view.cash,
        positions_value=view.positions_value,
        portfolios=[ConsolidatedPortfolioOut(**p.__dict__) for p in view.portfolios],
        by_portfolio=_slices(view.by_portfolio),
        by_asset_class=_slices(view.by_asset_class),
        by_instrument=_slices(view.by_instrument),
        by_currency=_slices(view.by_currency),
        unconverted_currencies=view.unconverted_currencies,
        has_missing_prices=view.has_missing_prices,
    )


# ---------------------------------------------------------------------------
# Realized gains and income
# ---------------------------------------------------------------------------


@router.get("/portfolios/{portfolio_id}/analytics/realized", response_model=RealizedOut)
def get_realized(
    portfolio_id: str,
    year: int | None = Query(default=None, ge=1970, le=2100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RealizedOut:
    analytics_requests_total.labels(endpoint="realized").inc()
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    report = realized_report(db, portfolio, year)
    return RealizedOut(
        base_currency=report.base_currency,
        year=year,
        sales=[RealizedSaleOut(**s.__dict__) for s in report.sales],
        by_year=[RealizedTotalOut(**t.__dict__) for t in report.by_year],
        by_instrument=[RealizedTotalOut(**t.__dict__) for t in report.by_instrument],
        total_realized_pnl_base=report.total_realized_pnl_base,
        unconverted_currencies=report.unconverted_currencies,
        mixed_currency_sales=report.mixed_currency_sales,
        method=report.method,
    )


@router.get("/portfolios/{portfolio_id}/analytics/income", response_model=IncomeOut)
def get_income(
    portfolio_id: str,
    year: int | None = Query(default=None, ge=1970, le=2100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IncomeOut:
    analytics_requests_total.labels(endpoint="income").inc()
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    report = income_report(db, portfolio, year)

    def total(t) -> IncomeTotalOut:
        return IncomeTotalOut(
            key=t.key,
            label=t.label,
            income_base=t.income_base,
            fees_base=t.fees_base,
            net_base=t.net_base,
            count=t.count,
        )

    return IncomeOut(
        base_currency=report.base_currency,
        year=year,
        rows=[IncomeRowOut(**r.__dict__) for r in report.rows],
        by_year=[total(t) for t in report.by_year],
        by_month=[total(t) for t in report.by_month],
        by_instrument=[total(t) for t in report.by_instrument],
        total_income_base=report.total_income_base,
        total_fees_base=report.total_fees_base,
        unconverted_currencies=report.unconverted_currencies,
        method=report.method,
    )


# ---------------------------------------------------------------------------
# Strategy study (educational backtest) and rebased comparison
# ---------------------------------------------------------------------------


@router.get("/instruments/{instrument_id}/analytics/strategy-study", response_model=StrategyStudyOut)
def get_strategy_study(
    instrument_id: str,
    rule: str = Query(default="sma_cross"),
    days: int = Query(default=730, ge=90, le=3660),
    fast: int = Query(default=20, ge=2, le=200),
    slow: int = Query(default=50, ge=3, le=400),
    rsi_period: int = Query(default=14, ge=2, le=100),
    rsi_low: float = Query(default=30.0, ge=1, le=50),
    rsi_high: float = Query(default=70.0, ge=50, le=99),
    fee_bps: float = Query(default=10.0, ge=0, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyStudyOut:
    analytics_requests_total.labels(endpoint="strategy_study").inc()
    if rule not in quant.STRATEGY_RULES:
        raise HTTPException(status_code=422, detail=f"rule must be one of {', '.join(quant.STRATEGY_RULES)}")
    if rule == "sma_cross" and fast >= slow:
        raise HTTPException(status_code=422, detail="fast must be shorter than slow")
    instrument = get_visible_instrument(instrument_id, db, user)
    series = _instrument_series(db, instrument, days)
    study = quant.strategy_study(
        [d for d, _ in series],
        [v for _, v in series],
        rule,
        fast=fast,
        slow=slow,
        rsi_period=rsi_period,
        rsi_low=rsi_low,
        rsi_high=rsi_high,
        fee_bps=fee_bps,
    )

    def stats(s):
        if s is None:
            return None
        return ReturnStatsOut(
            subject=f"instrument:{instrument.id}",
            label=instrument.symbol,
            currency=instrument.currency,
            start=_dt(series[0][0]) if series else None,
            end=_dt(series[-1][0]) if series else None,
            **s.__dict__,
        )

    return StrategyStudyOut(
        instrument_id=instrument.id,
        symbol=instrument.symbol,
        currency=instrument.currency,
        has_sufficient_data=study.has_sufficient_data,
        observations=study.observations,
        rule=study.rule,
        params=study.params,
        fee_bps=study.fee_bps,
        dates=[_dt(d) for d in study.dates],
        strategy_equity=study.strategy_equity,
        benchmark_equity=study.benchmark_equity,
        invested=study.invested,
        trades=[
            StrategyTradeOut(
                entry_date=_dt(t.entry_date),
                exit_date=_dt(t.exit_date) if t.exit_date is not None else None,
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                return_pct=t.return_pct,
                holding_days=t.holding_days,
            )
            for t in study.trades
        ],
        n_trades=study.n_trades,
        exposure_share=study.exposure_share,
        win_rate=study.win_rate,
        strategy_stats=stats(study.strategy_stats),
        benchmark_stats=stats(study.benchmark_stats),
        method=study.method,
        disclaimer=study.disclaimer,
    )


@router.get("/market/compare", response_model=CompareOut)
def compare_instruments(
    instrument_ids: str = Query(min_length=1, description="comma-separated instrument ids"),
    days: int = Query(default=365, ge=30, le=3660),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompareOut:
    """Rebased (base 100) closes of up to six visible instruments on their
    common dates — relative paths, deliberately not amounts."""
    analytics_requests_total.labels(endpoint="compare").inc()
    ids = [i.strip() for i in instrument_ids.split(",") if i.strip()]
    ids = list(dict.fromkeys(ids))
    if not ids or len(ids) > MAX_COMPARE_INSTRUMENTS:
        raise HTTPException(status_code=422, detail=f"between 1 and {MAX_COMPARE_INSTRUMENTS} instrument ids")
    instruments = [get_visible_instrument(i, db, user) for i in ids]
    raw = {inst.id: _instrument_series(db, inst, days) for inst in instruments}
    dates, rebased = quant.rebase_series(raw)
    series = []
    for inst in instruments:
        values = rebased.get(inst.id, [])
        series.append(
            CompareSeriesOut(
                instrument=InstrumentOut.from_model(inst),
                values=values,
                total_return=(values[-1] / values[0] - 1.0) if len(values) > 1 and values[0] else None,
            )
        )
    return CompareOut(
        dates=[_dt(d) for d in dates],
        base=100.0,
        series=series,
        observations=len(dates),
        method="clôtures quotidiennes sur les dates communes à tous les instruments, rebasées à 100 le premier jour "
        "commun ; chaque série reste dans sa propre devise (trajectoires relatives, pas des montants)",
    )


# ---------------------------------------------------------------------------
# Informational alerts and notifications
# ---------------------------------------------------------------------------


def _alert_out(alert: PriceAlert) -> AlertOut:
    return AlertOut(
        id=alert.id,
        instrument=InstrumentOut.from_model(alert.instrument),
        kind=alert.kind,
        kind_label=KIND_LABELS[alert.kind],
        threshold=alert.threshold,
        note=alert.note,
        active=alert.active,
        created_at=alert.created_at,
        triggered_at=alert.triggered_at,
        last_evaluated_at=alert.last_evaluated_at,
        last_value=alert.last_value,
    )


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    instrument_id: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[AlertOut]:
    query = select(PriceAlert).where(PriceAlert.user_id == user.id)
    if instrument_id:
        query = query.where(PriceAlert.instrument_id == instrument_id)
    alerts = db.scalars(query.order_by(PriceAlert.active.desc(), PriceAlert.created_at.desc())).all()
    return [_alert_out(a) for a in alerts]


@router.post("/alerts", response_model=AlertOut, status_code=201)
def create_alert(
    payload: AlertCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> AlertOut:
    instrument = get_visible_instrument(payload.instrument_id, db, user)
    count = db.scalar(select(func.count()).select_from(PriceAlert).where(PriceAlert.user_id == user.id)) or 0
    if count >= MAX_ALERTS_PER_USER:
        raise HTTPException(status_code=422, detail=f"at most {MAX_ALERTS_PER_USER} alerts per user")
    alert = PriceAlert(
        user_id=user.id, instrument_id=instrument.id, kind=payload.kind, threshold=payload.threshold, note=payload.note
    )
    db.add(alert)
    db.add(AuditEvent(user_id=user.id, action="alert.create", target_type="price_alert", target_id=alert.id))
    db.commit()
    # Evaluate right away against stored data: a threshold already crossed
    # notifies immediately instead of at the next worker cycle.
    evaluate_alerts(db, user.id)
    db.refresh(alert)
    return _alert_out(alert)


@router.post("/alerts/{alert_id}/rearm", response_model=AlertOut)
def rearm_alert(
    alert_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> AlertOut:
    alert = db.get(PriceAlert, alert_id)
    if alert is None or alert.user_id != user.id:
        raise HTTPException(status_code=404, detail="alert not found")
    alert.active = True
    alert.triggered_at = None
    db.commit()
    evaluate_alerts(db, user.id)
    db.refresh(alert)
    return _alert_out(alert)


@router.delete("/alerts/{alert_id}", status_code=204)
def delete_alert(
    alert_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> None:
    alert = db.get(PriceAlert, alert_id)
    if alert is None or alert.user_id != user.id:
        raise HTTPException(status_code=404, detail="alert not found")
    db.delete(alert)
    db.add(AuditEvent(user_id=user.id, action="alert.delete", target_type="price_alert", target_id=alert_id))
    db.commit()


@router.get("/notifications", response_model=NotificationsOut)
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationsOut:
    """Also evaluates the caller's active alerts against stored data (DB
    only, no provider call) so a fresh worker refresh is reflected at once."""
    evaluate_alerts(db, user.id)
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    items = db.scalars(query.order_by(Notification.created_at.desc()).limit(limit)).all()
    unread = (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
        or 0
    )
    items_out = [NotificationOut.model_validate(n, from_attributes=True) for n in items]
    return NotificationsOut(items=items_out, unread=unread)


@router.post("/notifications/read", response_model=NotificationsOut)
def mark_notifications_read(
    payload: MarkReadRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> NotificationsOut:
    query = select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if payload.ids:
        query = query.where(Notification.id.in_(payload.ids))
    now = datetime.now(UTC)
    for notification in db.scalars(query):
        notification.read_at = now
    db.commit()
    return list_notifications(unread_only=False, limit=50, user=user, db=db)


@router.delete("/notifications/{notification_id}", status_code=204)
def delete_notification(
    notification_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> None:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(status_code=404, detail="notification not found")
    db.delete(notification)
    db.commit()
