from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_csrf
from app.domain.analytics import compute_indicators
from app.domain.positions import record_private_valuation
from app.models import Instrument, PricePoint, PrivateValuation, User
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


def _get_owned_instrument(instrument_id: str, db: Session, user: User) -> Instrument:
    instrument = db.get(Instrument, instrument_id)
    if instrument is None or instrument.user_id != user.id:
        raise HTTPException(status_code=404, detail="instrument not found")
    return instrument


@router.get("", response_model=list[InstrumentOut])
def list_instruments(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[InstrumentOut]:
    instruments = db.scalars(select(Instrument).where(Instrument.user_id == user.id).order_by(Instrument.symbol)).all()
    return [InstrumentOut.model_validate(i) for i in instruments]


@router.get("/search", response_model=list[InstrumentOut])
def search_instruments(
    q: str = Query(min_length=1, max_length=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[InstrumentOut]:
    """Searches only the caller's own instrument catalog in V1 — there is no
    external instrument database wired in yet (see app/adapters/market_data.py)."""
    pattern = f"%{q}%"
    instruments = db.scalars(
        select(Instrument)
        .where(Instrument.user_id == user.id)
        .where((Instrument.symbol.ilike(pattern)) | (Instrument.name.ilike(pattern)))
        .order_by(Instrument.symbol)
        .limit(50)
    ).all()
    return [InstrumentOut.model_validate(i) for i in instruments]


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
        currency=payload.currency,
    )
    db.add(instrument)
    db.commit()
    return InstrumentOut.model_validate(instrument)


@router.get("/{instrument_id}", response_model=InstrumentOut)
def get_instrument(
    instrument_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> InstrumentOut:
    instrument = _get_owned_instrument(instrument_id, db, user)
    return InstrumentOut.model_validate(instrument)


@router.get("/{instrument_id}/prices", response_model=list[PricePointOut])
def list_prices(
    instrument_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[PricePointOut]:
    _get_owned_instrument(instrument_id, db, user)
    prices = db.scalars(
        select(PricePoint).where(PricePoint.instrument_id == instrument_id).order_by(PricePoint.as_of.desc())
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
    """Manual price entry — the only way a position gets a market value
    today, since no real market-data provider is wired in (see
    app/adapters/market_data.py)."""
    _get_owned_instrument(instrument_id, db, user)
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IndicatorsOut:
    """specs/ANALYTICS_AND_CHARTS.md: "Indicateurs : SMA/EMA/RSI/MACD, avec
    paramètres visibles et aucune alerte prescriptive" — window sizes are
    caller-supplied and echoed back in the response, never hidden."""
    _get_owned_instrument(instrument_id, db, user)
    prices = db.scalars(
        select(PricePoint).where(PricePoint.instrument_id == instrument_id).order_by(PricePoint.as_of)
    ).all()
    series = compute_indicators(
        dates=[p.as_of for p in prices],
        prices=[p.price for p in prices],
        sma_window=sma,
        ema_window=ema,
        rsi_window=rsi,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal_window=macd_signal,
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
    )


@router.get("/{instrument_id}/private-valuations", response_model=list[PrivateValuationOut])
def list_private_valuations(
    instrument_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[PrivateValuationOut]:
    _get_owned_instrument(instrument_id, db, user)
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
    instrument = _get_owned_instrument(instrument_id, db, user)
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
