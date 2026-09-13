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
from app.market.ratelimit import TTLCache
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
    HolderViewOut,
    HorizonOut,
    LevelsOut,
    OrientationStatsOut,
    PastValidationOut,
    PortfolioCheckupOut,
    SignalOut,
    TallyOut,
    TargetAllocationUpdate,
    TimelinePointOut,
    VerdictOut,
)
from app.schemas.instruments import InstrumentOut
from app.schemas.portfolios import PortfolioOut

router = APIRouter(prefix="/api/v1", tags=["decision-aid"])

# 12-month momentum needs 273 closes; 450 calendar days leaves a margin for
# holidays and a partially filled cache.
SERIES_DAYS = 450
# Past validation is a few seconds of numpy per instrument: memoised per
# (instrument, horizon, last bar) so re-opening the tab is free.
_past_cache = TTLCache(ttl_seconds=3600, max_entries=256)


def _bars(db: Session, instrument: Instrument, days: int) -> list[OhlcBar]:
    since = datetime.now(UTC) - timedelta(days=days)
    return list(
        db.scalars(
            select(OhlcBar)
            .where(OhlcBar.instrument_id == instrument.id, OhlcBar.as_of >= since)
            .order_by(OhlcBar.as_of)
        )
    )


def _verdict_out(v: decision.Verdict) -> VerdictOut:
    return VerdictOut(orientation_label=decision.ORIENTATION_LABELS[v.orientation], **v.__dict__)


def _watch_item(db: Session, user: User, instrument_id: str) -> WatchlistItem | None:
    return db.scalars(
        select(WatchlistItem).where(WatchlistItem.user_id == user.id, WatchlistItem.instrument_id == instrument_id)
    ).first()


def _dt(d) -> datetime:
    return d if isinstance(d, datetime) else datetime.combine(d, datetime.min.time(), tzinfo=UTC)


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
    capital: float = Query(default=10_000.0, ge=100, le=1e9),
    risk_pct: float = Query(default=1.0, ge=0.1, le=10),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DecisionAidOut:
    analytics_requests_total.labels(endpoint="decision_aid").inc()
    instrument = get_visible_instrument(instrument_id, db, user)
    series = _instrument_series(db, instrument, SERIES_DAYS)  # tops up the bar cache
    closes = [v for _, v in series]
    signals = decision.technical_signals(closes)
    bars = _bars(db, instrument, SERIES_DAYS)
    if bars and len(bars) == len(closes) and all(b.high is not None and b.low is not None for b in bars):
        highs, lows = [float(b.high) for b in bars], [float(b.low) for b in bars]
    else:
        highs = lows = None

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
    vs = decision.verdicts(signals)
    orientation, confidence, orientation_text = decision.overall_orientation(vs)
    levels = decision.compute_levels(closes, highs, lows, capital=capital, risk_pct=risk_pct) if closes else None
    item = _watch_item(db, user, instrument.id)
    holder = None
    if item is not None and item.held:
        hv = decision.holder_view(orientation, levels, float(item.entry_price) if item.entry_price else None)
        holder = HolderViewOut(held=True, **hv.__dict__)
    last_bar = bars[-1] if bars else None
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
        verdicts=[_verdict_out(v) for v in vs],
        orientation=orientation,
        orientation_label=decision.ORIENTATION_LABELS[orientation],
        orientation_confidence=confidence,
        orientation_text=orientation_text,
        levels=LevelsOut(**levels.__dict__) if levels else None,
        holder=holder,
        fundamentals=_fundamentals_status(fundamentals),
        prediction_available=prediction is not None,
        news_last_7_days=_news_count(db, instrument.id),
        disclaimer=aid.disclaimer,
    )


@router.get("/instruments/{instrument_id}/decision-aid/past", response_model=PastValidationOut)
def decision_aid_past_validation(
    instrument_id: str,
    horizon_days: int = Query(default=20, ge=5, le=120),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PastValidationOut:
    """How the short-term readings would have fared on this instrument's own
    past: computed date by date with only prior data, then compared with
    the return that followed — and with 'buy any day' as the baseline."""
    analytics_requests_total.labels(endpoint="decision_aid_past").inc()
    instrument = get_visible_instrument(instrument_id, db, user)
    series = _instrument_series(db, instrument, 365 * 4)
    key = (instrument.id, horizon_days, series[-1][0].isoformat() if series else None, len(series))
    result = _past_cache.get(key)
    if result is None:
        result = decision.past_validation([d for d, _ in series], [v for _, v in series], horizon_days=horizon_days)
        _past_cache.set(key, result)
    return PastValidationOut(
        instrument_id=instrument.id,
        symbol=instrument.symbol,
        horizon_days=result.horizon_days,
        evaluations=result.evaluations,
        start=_dt(result.start) if result.start else None,
        end=_dt(result.end) if result.end else None,
        by_orientation=[OrientationStatsOut(**b.__dict__) for b in result.by_orientation],
        baseline_mean_return=result.baseline_mean_return,
        baseline_hit_rate=result.baseline_hit_rate,
        timeline=[TimelinePointOut(as_of=_dt(d), orientation=o, close=c) for d, o, c in result.timeline],
        text=result.text,
        method=result.method,
        disclaimer=decision.DISCLAIMER,
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
    watch_items = db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == user.id)).all()
    watched = {w.instrument_id for w in watch_items}
    held_watch = {w.instrument_id for w in watch_items if w.held}
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
        orientation, confidence, _ = decision.overall_orientation(decision.verdicts(signals))
        rsi = by_key.get("rsi")
        entries.append(
            DecisionOverviewEntry(
                instrument=InstrumentOut.from_model(instrument),
                held=instrument.id in held or instrument.id in held_watch,
                watched=instrument.id in watched,
                orientation=orientation,
                orientation_label=decision.ORIENTATION_LABELS[orientation],
                orientation_confidence=confidence,
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
