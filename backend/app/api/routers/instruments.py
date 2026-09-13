"""Instruments: private definitions (manual prices, private valuations),
read access to any visible catalog entry, and technical indicators computed
on the stored daily series. Quoted instruments are discovered/added through
app/api/routers/market.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_owned_instrument, get_visible_instrument, require_csrf
from app.domain.analytics import compute_indicators
from app.domain.positions import record_private_valuation
from app.domain.quant import compute_extended_indicators
from app.market import service as market_service
from app.models import Instrument, OhlcBar, Portfolio, PositionLot, PricePoint, PrivateValuation, User, WatchlistItem
from app.schemas.analytics import IndicatorsOut
from app.schemas.instruments import (
    InstrumentCreate,
    InstrumentOut,
    PricePointCreate,
    PricePointOut,
    PrivateValuationCreate,
    PrivateValuationOut,
)

router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])


def _price_series(db: Session, instrument: Instrument, days: int | None = None):
    """Daily closes when the instrument has bars, else its price points —
    one observation per day (the latest), oldest first."""
    start = datetime.now(UTC) - timedelta(days=days) if days else None
    bars_query = select(OhlcBar).where(OhlcBar.instrument_id == instrument.id).order_by(OhlcBar.as_of)
    points_query = select(PricePoint).where(PricePoint.instrument_id == instrument.id).order_by(PricePoint.as_of)
    if start is not None:
        bars_query = bars_query.where(OhlcBar.as_of >= start)
        points_query = points_query.where(PricePoint.as_of >= start)
    bars = db.scalars(bars_query).all()
    if bars:
        return [b.as_of for b in bars], [b.close for b in bars], bars
    points = db.scalars(points_query).all()
    by_day: dict = {}
    for p in points:
        by_day[p.as_of.date()] = p
    ordered = [by_day[d] for d in sorted(by_day)]
    return [p.as_of for p in ordered], [p.price for p in ordered], None


@router.get("", response_model=list[InstrumentOut])
def list_instruments(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[InstrumentOut]:
    """The caller's working set: private instruments plus every catalog
    entry they hold or watch (the shared catalog itself is browsed via
    /market/search)."""
    own = select(Instrument.id).where(Instrument.user_id == user.id)
    held = (
        select(PositionLot.instrument_id)
        .join(Portfolio, Portfolio.id == PositionLot.portfolio_id)
        .where(Portfolio.user_id == user.id)
    )
    watched = select(WatchlistItem.instrument_id).where(WatchlistItem.user_id == user.id)
    ids = {r[0] for r in db.execute(own)} | {r[0] for r in db.execute(held)} | {r[0] for r in db.execute(watched)}
    if not ids:
        return []
    instruments = db.scalars(select(Instrument).where(Instrument.id.in_(ids)).order_by(Instrument.symbol)).all()
    return [InstrumentOut.from_model(i) for i in instruments]


@router.post("", response_model=InstrumentOut, status_code=201)
def create_instrument(
    payload: InstrumentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> InstrumentOut:
    existing = db.scalars(
        select(Instrument).where(Instrument.user_id == user.id, Instrument.symbol == payload.symbol)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="an instrument with this symbol already exists")
    instrument = Instrument(
        user_id=user.id,
        symbol=payload.symbol,
        name=payload.name,
        asset_class=payload.asset_class,
        isin=payload.isin,
        exchange=payload.exchange,
        currency=payload.currency,
        provider="manual",
        provider_symbol=None,
    )
    db.add(instrument)
    db.commit()
    return InstrumentOut.from_model(instrument)


@router.get("/{instrument_id}", response_model=InstrumentOut)
def get_instrument(
    instrument_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> InstrumentOut:
    return InstrumentOut.from_model(get_visible_instrument(instrument_id, db, user))


@router.delete("/{instrument_id}", status_code=204)
def delete_instrument(
    instrument_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> None:
    """Private instruments only, and only while no transaction references them."""
    instrument = get_owned_instrument(instrument_id, db, user)
    from app.models import Transaction

    if db.scalars(select(Transaction.id).where(Transaction.instrument_id == instrument.id).limit(1)).first():
        raise HTTPException(status_code=409, detail="instrument is referenced by transactions")
    db.delete(instrument)
    db.commit()


@router.get("/{instrument_id}/prices", response_model=list[PricePointOut])
def list_prices(
    instrument_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[PricePointOut]:
    get_visible_instrument(instrument_id, db, user)
    prices = db.scalars(
        select(PricePoint).where(PricePoint.instrument_id == instrument_id).order_by(PricePoint.as_of.desc()).limit(500)
    ).all()
    return [PricePointOut.model_validate(p) for p in prices]


@router.post("/{instrument_id}/prices", response_model=PricePointOut, status_code=201)
def create_price(
    instrument_id: str,
    payload: PricePointCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> PricePointOut:
    """Manual price entry for a private instrument (shared catalog entries
    are priced by their provider and read-only for users)."""
    get_owned_instrument(instrument_id, db, user)
    price = PricePoint(
        instrument_id=instrument_id,
        as_of=payload.as_of,
        price=payload.price,
        currency=payload.currency,
        source="manual",
        is_estimate=payload.is_estimate,
    )
    db.add(price)
    db.commit()
    return PricePointOut.model_validate(price)


@router.get("/{instrument_id}/indicators", response_model=IndicatorsOut)
def get_indicators(
    instrument_id: str,
    sma: int = Query(default=20, ge=2, le=200),
    ema: int = Query(default=12, ge=2, le=200),
    rsi: int = Query(default=14, ge=2, le=200),
    macd_fast: int = Query(default=12, ge=2, le=200),
    macd_slow: int = Query(default=26, ge=2, le=200),
    macd_signal: int = Query(default=9, ge=2, le=200),
    bollinger: int = Query(default=20, ge=2, le=200),
    bollinger_k: float = Query(default=2.0, gt=0, le=5),
    atr: int = Query(default=14, ge=2, le=200),
    stochastic: int = Query(default=14, ge=2, le=200),
    days: int | None = Query(default=None, ge=30, le=3660),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IndicatorsOut:
    """specs/ANALYTICS_AND_CHARTS.md: parameters are caller-supplied and
    echoed back, never hidden; every series is None until its window fills."""
    instrument = get_visible_instrument(instrument_id, db, user)
    if instrument.user_id is None and days:
        # Make sure the stored series covers what's asked (cache-first, at most one provider call).
        market_service.get_history(db, instrument, datetime.now(UTC) - timedelta(days=days), datetime.now(UTC))
    dates, prices, bars = _price_series(db, instrument, days)
    series = compute_indicators(
        dates=dates,
        prices=prices,
        sma_window=sma,
        ema_window=ema,
        rsi_window=rsi,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal_window=macd_signal,
    )
    extended = compute_extended_indicators(
        closes=prices,
        highs=[b.high for b in bars] if bars else None,
        lows=[b.low for b in bars] if bars else None,
        volumes=[b.volume for b in bars] if bars else None,
        bollinger_window=bollinger,
        bollinger_k=bollinger_k,
        atr_window=atr,
        stochastic_window=stochastic,
    )
    return IndicatorsOut(
        dates=series.dates,
        prices=series.prices,
        sma=series.sma,
        ema=series.ema,
        rsi=series.rsi,
        macd=series.macd,
        macd_signal=series.macd_signal,
        sma_window=sma,
        ema_window=ema,
        rsi_window=rsi,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal_window=macd_signal,
        bollinger_upper=extended.bollinger_upper,
        bollinger_middle=extended.bollinger_middle,
        bollinger_lower=extended.bollinger_lower,
        bollinger_window=bollinger,
        bollinger_k=bollinger_k,
        atr=extended.atr,
        atr_window=atr,
        stochastic_k=extended.stochastic_k,
        stochastic_d=extended.stochastic_d,
        stochastic_window=stochastic,
        obv=extended.obv,
        has_ohlc=bars is not None and bool(bars) and all(b.high is not None for b in bars),
    )


@router.get("/{instrument_id}/private-valuations", response_model=list[PrivateValuationOut])
def list_private_valuations(
    instrument_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[PrivateValuationOut]:
    get_visible_instrument(instrument_id, db, user)
    valuations = db.scalars(
        select(PrivateValuation)
        .where(PrivateValuation.instrument_id == instrument_id)
        .order_by(PrivateValuation.valuation_date.desc())
    ).all()
    return [PrivateValuationOut.model_validate(v) for v in valuations]


@router.post("/{instrument_id}/private-valuations", response_model=PrivateValuationOut, status_code=201)
def create_private_valuation(
    instrument_id: str,
    payload: PrivateValuationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> PrivateValuationOut:
    """specs/PRODUCT_SPEC.md: private-asset valuations require an explicit
    date, amount, method and confidence — never inferred silently."""
    instrument = get_owned_instrument(instrument_id, db, user)
    try:
        valuation = record_private_valuation(
            db,
            instrument,
            valuation_date=payload.valuation_date,
            amount=payload.valuation_amount,
            currency=payload.currency,
            method=payload.method,
            confidence=payload.confidence,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return PrivateValuationOut.model_validate(valuation)
