"""Decision aid endpoints: one button, every recognised reading.

- `GET /instruments/{id}/decision-aid`: technical, fundamental, risk and
  (if an experiment exists) prediction readings of one instrument.
- `GET /market/decision-overview`: the short version for everything the
  user holds or watches, from *cached* data only (no provider call).
- `GET /portfolios/{id}/checkup` + `PATCH /portfolios/{id}/targets`: the
  portfolio's structure against textbook diversification rules and the
  user's own target allocation.

Readings are generic and counted, never weighted into a verdict; the
response carries the disclaimer the UI must show (specs/PRODUCT_SPEC.md:
information, not personalised advice, no execution).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_owned_portfolio, get_visible_instrument, require_csrf
from app.api.routers.analytics import _instrument_series, _portfolio_series
from app.config import settings
from app.domain import decision, quant
from app.domain.positions import compute_positions, compute_valuation
from app.market import service as market_service
from app.models import (
    AuditEvent,
    Instrument,
    InstrumentFundamentals,
    NewsItem,
    NewsItemAsset,
    OhlcBar,
    Portfolio,
    PositionLot,
    PredictionExperiment,
    User,
    WatchlistItem,
)
from app.observability.metrics import analytics_requests_total
from app.schemas.decision import (
    AllocationShareOut,
    DecisionAidOut,
    DecisionOverviewEntry,
    DecisionOverviewOut,
    FundamentalsStatusOut,
    HorizonOut,
    PortfolioCheckupOut,
    SignalOut,
    TallyOut,
    TargetAllocationUpdate,
)
from app.schemas.instruments import InstrumentOut
from app.schemas.portfolios import PortfolioOut

router = APIRouter(prefix="/api/v1", tags=["decision-aid"])

# 12-month momentum needs 273 closes; 450 calendar days leaves a margin for
# holidays and a partially filled cache.
SERIES_DAYS = 450


def _signal_out(s: decision.Signal) -> SignalOut:
    return SignalOut(**s.__dict__)


def _tally_out(t: decision.Tally) -> TallyOut:
    return TallyOut(
        favorable=t.favorable,
        defavorable=t.defavorable,
        neutre=t.neutre,
        indisponible=t.indisponible,
        available=t.available,
    )


def _latest_experiment(db: Session, user: User, instrument_id: str) -> PredictionExperiment | None:
    return db.scalars(
        select(PredictionExperiment)
        .where(
            PredictionExperiment.user_id == user.id,
            PredictionExperiment.instrument_id == instrument_id,
            PredictionExperiment.status == "completed",
        )
        .order_by(PredictionExperiment.trained_at.desc())
        .limit(1)
    ).first()


def _news_count(db: Session, instrument_id: str, days: int = 7) -> int:
    since = datetime.now(UTC) - timedelta(days=days)
    return (
        db.scalar(
            select(func.count(func.distinct(NewsItemAsset.news_item_id)))
            .select_from(NewsItemAsset)
            .join(NewsItem, NewsItem.id == NewsItemAsset.news_item_id)
            .where(NewsItemAsset.instrument_id == instrument_id, NewsItem.publication_at >= since)
        )
        or 0
    )


def _fundamentals_status(view: market_service.FundamentalsView) -> FundamentalsStatusOut:
    row = view.row
    return FundamentalsStatusOut(
        status=view.status,
        reason=view.reason,
        provider=view.provider,
        as_of=row.as_of if row else None,
        source=row.source if row else None,
        license_note=(row.data or {}).get("license_note") if row else None,
        env_var=settings.finnhub_api_key_env_var if view.provider == "finnhub" else None,
    )


@router.get("/instruments/{instrument_id}/decision-aid", response_model=DecisionAidOut)
def instrument_decision_aid(
    instrument_id: str,
    refresh_fundamentals: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DecisionAidOut:
    analytics_requests_total.labels(endpoint="decision_aid").inc()
    instrument = get_visible_instrument(instrument_id, db, user)
    series = _instrument_series(db, instrument, SERIES_DAYS)
    closes = [v for _, v in series]
    signals = decision.technical_signals(closes)

    fundamentals = market_service.get_fundamentals(db, instrument, force=refresh_fundamentals)
    if instrument.asset_class in market_service.FUNDAMENTALS_ASSET_CLASSES and instrument.user_id is None:
        signals += decision.fundamental_signals(fundamentals.row.data if fundamentals.row else None)

    experiment = _latest_experiment(db, user, instrument.id)
    prediction = None
    if experiment is not None:
        prediction = decision.prediction_signal(
            experiment.latest_forecast, experiment.metrics, (experiment.config or {}).get("horizon_days")
        )
        if prediction is not None:
            signals.append(prediction)

    aid = decision.summarize_instrument(signals)
    last_bar = db.scalars(
        select(OhlcBar).where(OhlcBar.instrument_id == instrument.id).order_by(OhlcBar.as_of.desc()).limit(1)
    ).first()
    return DecisionAidOut(
        instrument=InstrumentOut.from_model(instrument),
        as_of=datetime.now(UTC),
        observations=len(closes),
        price_source=last_bar.source if last_bar else None,
        signals=[_signal_out(s) for s in aid.signals],
        tally=_tally_out(aid.tally),
        horizons=[
            HorizonOut(horizon=h.horizon, label=h.label, tally=_tally_out(h.tally), text=h.text) for h in aid.horizons
        ],
        overall=aid.overall,
        fundamentals=_fundamentals_status(fundamentals),
        prediction_available=prediction is not None,
        news_last_7_days=_news_count(db, instrument.id),
        disclaimer=aid.disclaimer,
    )


@router.get("/market/decision-overview", response_model=DecisionOverviewOut)
def market_decision_overview(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> DecisionOverviewOut:
    """Short readings for every held or watched instrument, computed from
    stored bars and the cached fundamentals only — opening this page never
    costs a provider request (the worker keeps tracked instruments fresh)."""
    analytics_requests_total.labels(endpoint="decision_overview").inc()
    held = {
        lot.instrument_id
        for lot in db.scalars(
            select(PositionLot)
            .join(Portfolio, Portfolio.id == PositionLot.portfolio_id)
            .where(Portfolio.user_id == user.id, PositionLot.quantity_remaining > 0)
        )
    }
    watched = {w.instrument_id for w in db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == user.id))}
    since = datetime.now(UTC) - timedelta(days=SERIES_DAYS)
    entries = []
    for instrument_id in sorted(held | watched):
        instrument = db.get(Instrument, instrument_id)
        if instrument is None:
            continue
        closes = [
            float(b.close)
            for b in db.scalars(
                select(OhlcBar)
                .where(OhlcBar.instrument_id == instrument.id, OhlcBar.as_of >= since)
                .order_by(OhlcBar.as_of)
            )
        ]
        signals = decision.technical_signals(closes)
        cached = db.get(InstrumentFundamentals, instrument.id)
        if cached is not None:
            signals += decision.fundamental_signals(cached.data)
        by_key = {s.key: s for s in signals}
        aid = decision.summarize_instrument(signals)
        rsi = by_key.get("rsi")
        entries.append(
            DecisionOverviewEntry(
                instrument=InstrumentOut.from_model(instrument),
                held=instrument.id in held,
                watched=instrument.id in watched,
                observations=len(closes),
                tally=_tally_out(aid.tally),
                trend=by_key["tendance_sma"].reading if "tendance_sma" in by_key else "indisponible",
                momentum=by_key["momentum_12_1"].reading if "momentum_12_1" in by_key else "indisponible",
                rsi=rsi.value if rsi else None,
                rsi_reading=rsi.reading if rsi else "indisponible",
                valuation=by_key["per"].reading if "per" in by_key else "indisponible",
                overall=aid.overall,
            )
        )
    return DecisionOverviewOut(
        entries=entries,
        fundamentals_configured=settings.market_fundamentals_provider != "null",
        disclaimer=decision.DISCLAIMER,
    )


@router.get("/portfolios/{portfolio_id}/checkup", response_model=PortfolioCheckupOut)
def portfolio_checkup(
    portfolio_id: str,
    days: int = Query(default=365, ge=90, le=1825),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioCheckupOut:
    analytics_requests_total.labels(endpoint="portfolio_checkup").inc()
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    positions = compute_positions(db, portfolio)
    valuation = compute_valuation(db, portfolio, positions)

    inputs = []
    for p in positions:
        value = p.market_value_base
        pnl_pct = None
        if p.unrealized_pnl is not None and p.cost_basis:
            pnl_pct = float(p.unrealized_pnl / p.cost_basis)
        inputs.append(
            decision.PositionInput(
                symbol=p.instrument.symbol,
                asset_class=p.instrument.asset_class,
                currency=p.currency,
                value_base=float(value) if value is not None else None,
                unrealized_pnl_pct=pnl_pct,
            )
        )

    # Average pairwise correlation and portfolio risk over the window, from
    # the same cached series the analytics page uses.
    avg_corr, pairs = None, 0
    if len(positions) >= 2:
        series = {p.instrument.symbol: _instrument_series(db, p.instrument, days) for p in positions}
        series = {k: v for k, v in series.items() if len(v) >= 2}
        _, aligned = quant.align_on_dates(series)
        corr = quant.correlation_matrix(aligned)
        if corr.has_sufficient_data and len(corr.labels) >= 2:
            n = len(corr.labels)
            values = [corr.matrix[i][j] for i in range(n) for j in range(i + 1, n) if corr.matrix[i][j] is not None]
            if values:
                avg_corr, pairs = sum(values) / len(values), len(values)
    end = datetime.now(UTC)
    history = _portfolio_series(db, portfolio, end - timedelta(days=days), end)
    stats = quant.return_stats([v for _, v in history])

    checkup = decision.portfolio_checkup(
        decision.CheckupInput(
            base_currency=portfolio.base_currency,
            positions=inputs,
            cash_base=float(valuation.cash),
            total_base=float(valuation.total_value),
            target_allocation=portfolio.target_allocation,
            avg_correlation=avg_corr,
            correlation_pairs=pairs,
            volatility_annualized=stats.volatility_annualized if stats.has_sufficient_data else None,
            max_drawdown=stats.max_drawdown if stats.has_sufficient_data else None,
            missing_prices=sum(1 for p in positions if p.market_value is None),
        )
    )
    targets = portfolio.target_allocation or {}
    labels = sorted(set(checkup.allocation) | set(targets))
    allocation = [
        AllocationShareOut(
            label=label,
            share=checkup.allocation.get(label, 0.0),
            target=targets.get(label),
            drift=checkup.drift.get(label),
        )
        for label in labels
    ]
    return PortfolioCheckupOut(
        portfolio_id=portfolio.id,
        base_currency=portfolio.base_currency,
        as_of=datetime.now(UTC),
        total_value=str(valuation.total_value),
        signals=[_signal_out(s) for s in checkup.signals],
        tally=_tally_out(checkup.tally),
        overall=checkup.overall,
        allocation=allocation,
        has_targets=bool(targets),
        disclaimer=checkup.disclaimer,
    )


@router.patch("/portfolios/{portfolio_id}/targets", response_model=PortfolioOut)
def set_target_allocation(
    portfolio_id: str,
    payload: TargetAllocationUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> PortfolioOut:
    """The user's own plan, stored only to measure the drift against it."""
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    portfolio.target_allocation = payload.target_allocation
    db.add(
        AuditEvent(
            user_id=user.id,
            portfolio_id=portfolio.id,
            action="portfolio.targets",
            target_type="portfolio",
            target_id=portfolio.id,
        )
    )
    db.commit()
    return PortfolioOut.model_validate(portfolio)
