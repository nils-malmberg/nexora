"""Markets: search any quoted instrument, add it to the shared catalog, get
its quote/history, keep a watchlist, and record a purchase in one click.

Nothing here places an order anywhere — "Ajouter au portefeuille" only
records a transaction the user types in (specs/PRODUCT_SPEC.md: no order
execution in V1, enforced by tests/integration/test_no_order_endpoints.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_db,
    get_owned_portfolio,
    get_visible_instrument,
    rate_limited,
    require_csrf,
)
from app.config import settings
from app.domain.positions import DuplicateTransactionError, apply_transaction, freshness_status, latest_observation
from app.market import service as market_service
from app.models import AuditEvent, Instrument, PositionLot, User, WatchlistItem
from app.observability.metrics import transactions_created_total
from app.schemas.instruments import InstrumentOut
from app.schemas.market import (
    BarOut,
    CandidateOut,
    CatalogAddOut,
    CatalogAddRequest,
    HistoryOut,
    MarketOverviewEntry,
    QuickBuyRequest,
    QuoteOut,
    SearchOut,
    WatchlistAddRequest,
    WatchlistItemOut,
    WatchlistUpdateRequest,
)
from app.schemas.transactions import TransactionCreate, TransactionOut

router = APIRouter(prefix="/api/v1/market", tags=["market"])

RANGES = {"1w": 7, "1m": 31, "3m": 93, "6m": 186, "1y": 366, "2y": 732, "5y": 1830, "max": None}


def quote_out(db: Session, instrument: Instrument, *, refresh: bool = True) -> QuoteOut:
    """Cached-first quote (see app/market/service.py); `refresh=False` only
    reads what's stored (used for list views so one page never fans out into
    N provider calls)."""
    if refresh and instrument.user_id is None:
        view = market_service.refresh_quote(db, instrument)
        point, status, reason = view.price, view.status, view.reason
        provider, license_note, attribution = view.provider, view.license_note, view.attribution
        previous_close = view.previous_close
    else:
        point = market_service.latest_price_point(db, instrument.id)
        status = "cached" if point else "unavailable"
        reason, provider, license_note, attribution, previous_close = None, instrument.provider, None, None, None

    obs = latest_observation(db, instrument.id)
    now = datetime.now(UTC)
    # Prefer the freshest observation (a daily bar can be newer than a stale quote row).
    if obs is not None and (point is None or obs.as_of > point.as_of):
        price, currency, as_of, source = obs.price, obs.currency, obs.as_of, obs.source
        is_delayed, is_estimate, collected_at = obs.is_delayed, obs.is_estimate, None
    elif point is not None:
        price, currency, as_of, source = Decimal(str(point.price)), point.currency, point.as_of, point.source
        is_delayed, is_estimate, collected_at = point.is_delayed, point.is_estimate, point.collected_at
    else:
        price = currency = as_of = source = collected_at = None
        is_delayed = is_estimate = False

    change_pct = None
    if price is not None and previous_close:
        change_pct = ((price - previous_close) / previous_close * 100).quantize(Decimal("0.01"))

    return QuoteOut(
        instrument_id=instrument.id,
        price=price,
        currency=currency,
        as_of=as_of,
        collected_at=collected_at,
        source=source,
        is_delayed=is_delayed,
        is_estimate=is_estimate,
        status=status,
        reason=reason,
        freshness=freshness_status(obs),
        age_seconds=(now - as_of).total_seconds() if as_of else None,
        previous_close=previous_close,
        change_pct=change_pct,
        provider=provider,
        license_note=license_note,
        attribution=attribution,
    )


@router.get("/search", response_model=SearchOut)
def search_market(
    q: str = Query(min_length=1, max_length=80),
    asset_class: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=25),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rl: None = Depends(rate_limited),
) -> SearchOut:
    outcome = market_service.search(db, user.id, q, asset_class=asset_class, limit=limit)
    return SearchOut(
        query=q,
        candidates=[CandidateOut(**c.__dict__) for c in outcome.candidates],
        providers_queried=outcome.providers_queried,
        provider_errors=outcome.provider_errors,
    )


@router.post("/catalog", response_model=CatalogAddOut, status_code=201)
def add_to_catalog(
    payload: CatalogAddRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
    _rl: None = Depends(rate_limited),
) -> CatalogAddOut:
    """Makes a search result a real shared-catalog instrument (idempotent)."""
    if payload.provider not in ("yahoo", "coingecko", "finnhub", "fixture"):
        raise HTTPException(status_code=422, detail="unknown provider")
    existing = db.scalars(
        select(Instrument).where(
            Instrument.provider == payload.provider, Instrument.provider_symbol == payload.provider_symbol
        )
    ).first()
    if existing is not None:
        return CatalogAddOut(instrument=InstrumentOut.from_model(existing), created=False, warning=None)
    try:
        instrument, warning = market_service.ensure_catalog_instrument(
            db,
            provider=payload.provider,
            provider_symbol=payload.provider_symbol,
            symbol=payload.symbol,
            name=payload.name,
            asset_class=payload.asset_class,
            currency=payload.currency,
            exchange=payload.exchange,
            isin=payload.isin,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.commit()
    return CatalogAddOut(instrument=InstrumentOut.from_model(instrument), created=True, warning=warning)


@router.get("/instruments/{instrument_id}/quote", response_model=QuoteOut)
def get_quote(
    instrument_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rl: None = Depends(rate_limited),
) -> QuoteOut:
    instrument = get_visible_instrument(instrument_id, db, user)
    return quote_out(db, instrument)


@router.get("/instruments/{instrument_id}/history", response_model=HistoryOut)
def get_history(
    instrument_id: str,
    range_: str = Query(default="1y", alias="range"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rl: None = Depends(rate_limited),
) -> HistoryOut:
    if range_ not in RANGES:
        raise HTTPException(status_code=400, detail=f"range must be one of {sorted(RANGES)}")
    instrument = get_visible_instrument(instrument_id, db, user)
    end = datetime.now(UTC)
    days = RANGES[range_] or settings.market_history_max_days
    start = end - timedelta(days=days)
    view = market_service.get_history(db, instrument, start, end)
    bars = [
        BarOut(as_of=b.as_of, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume) for b in view.bars
    ]
    return HistoryOut(
        instrument_id=instrument.id,
        interval="1d",
        currency=view.bars[-1].currency if view.bars else instrument.currency,
        start=start,
        end=end,
        bars=bars,
        has_ohlc=view.has_ohlc,
        source=view.source,
        status=view.status,
        reason=view.reason,
        license_note=view.license_note,
        attribution=view.attribution,
    )


# --- watchlist ---------------------------------------------------------------


def _watchlist_out(db: Session, item: WatchlistItem, *, refresh: bool) -> WatchlistItemOut:
    return WatchlistItemOut(
        id=item.id,
        instrument=InstrumentOut.from_model(item.instrument),
        quote=quote_out(db, item.instrument, refresh=refresh),
        held=item.held,
        entry_price=item.entry_price,
        entry_date=item.entry_date,
        quantity=item.quantity,
        note=item.note,
        created_at=item.created_at,
    )


@router.get("/watchlist", response_model=list[WatchlistItemOut])
def list_watchlist(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[WatchlistItemOut]:
    items = db.scalars(
        select(WatchlistItem).where(WatchlistItem.user_id == user.id).order_by(WatchlistItem.created_at)
    ).all()
    return [_watchlist_out(db, item, refresh=False) for item in items]


@router.post("/watchlist", response_model=WatchlistItemOut, status_code=201)
def add_to_watchlist(
    payload: WatchlistAddRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> WatchlistItemOut:
    instrument = get_visible_instrument(payload.instrument_id, db, user)
    existing = db.scalars(
        select(WatchlistItem).where(WatchlistItem.user_id == user.id, WatchlistItem.instrument_id == instrument.id)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="already in watchlist")
    item = WatchlistItem(user_id=user.id, instrument_id=instrument.id)
    db.add(item)
    db.commit()
    return _watchlist_out(db, item, refresh=True)


@router.patch("/watchlist/{item_id}", response_model=WatchlistItemOut)
def update_watchlist_item(
    item_id: str,
    payload: WatchlistUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> WatchlistItemOut:
    item = db.get(WatchlistItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="watchlist item not found")
    if payload.held is not None:
        item.held = payload.held
    if payload.clear_entry:
        item.entry_price = item.entry_date = item.quantity = None
    if payload.entry_price is not None:
        item.entry_price = payload.entry_price
    if payload.entry_date is not None:
        item.entry_date = payload.entry_date
    if payload.quantity is not None:
        item.quantity = payload.quantity
    if payload.note is not None:
        item.note = payload.note or None
    db.commit()
    return _watchlist_out(db, item, refresh=False)


@router.delete("/watchlist/{item_id}", status_code=204)
def remove_from_watchlist(
    item_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> None:
    item = db.get(WatchlistItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="watchlist item not found")
    db.delete(item)
    db.commit()


# --- one-click purchase record ---------------------------------------------


@router.post("/instruments/{instrument_id}/quick-buy", response_model=TransactionOut, status_code=201)
def quick_buy(
    instrument_id: str,
    payload: QuickBuyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> TransactionOut:
    """Records an `achat` transaction for a visible instrument in one of the
    caller's portfolios. It is bookkeeping only: no broker, no execution."""
    instrument = get_visible_instrument(instrument_id, db, user)
    portfolio = get_owned_portfolio(payload.portfolio_id, db, user)
    trade_date = payload.trade_date or datetime.now(UTC)
    tx_payload = TransactionCreate(
        instrument_id=instrument.id,
        type="achat",
        trade_date=trade_date,
        quantity=payload.quantity,
        unit_price=payload.unit_price,
        currency=payload.currency,
        fees=payload.fees,
        note=payload.note,
    )
    try:
        if payload.fund_with_deposit:
            amount = payload.quantity * payload.unit_price + payload.fees
            apply_transaction(
                db,
                portfolio,
                None,
                TransactionCreate(
                    type="depot",
                    trade_date=trade_date - timedelta(microseconds=1),
                    quantity=Decimal("1"),
                    unit_price=amount,
                    currency=payload.currency,
                    note=f"Apport lié à l'achat de {instrument.symbol}",
                ),
            )
        tx = apply_transaction(db, portfolio, instrument, tx_payload)
    except DuplicateTransactionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.add(
        AuditEvent(
            user_id=user.id,
            portfolio_id=portfolio.id,
            action="transaction.quick_buy",
            target_type="transaction",
            target_id=tx.id,
        )
    )
    db.commit()
    transactions_created_total.labels(type="achat").inc()
    return TransactionOut.model_validate(tx)


# --- overview: everything the user tracks, with cached quotes -----------------


@router.get("/overview", response_model=list[MarketOverviewEntry])
def market_overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[MarketOverviewEntry]:
    """Held + watched instruments with their *cached* quotes (the worker
    refreshes them every `market_refresh_interval_seconds`)."""
    from app.models import Portfolio

    held: dict[str, Decimal] = {}
    for lot in db.scalars(
        select(PositionLot)
        .join(Portfolio, Portfolio.id == PositionLot.portfolio_id)
        .where(Portfolio.user_id == user.id, PositionLot.quantity_remaining > 0)
    ):
        held[lot.instrument_id] = held.get(lot.instrument_id, Decimal("0")) + Decimal(str(lot.quantity_remaining))
    watched = {w.instrument_id for w in db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == user.id))}
    ids = sorted(set(held) | watched)
    entries = []
    for instrument_id in ids:
        instrument = db.get(Instrument, instrument_id)
        if instrument is None:
            continue
        entries.append(
            MarketOverviewEntry(
                instrument=InstrumentOut.from_model(instrument),
                quote=quote_out(db, instrument, refresh=False),
                held_quantity=held.get(instrument_id),
                watched=instrument_id in watched,
            )
        )
    return entries
