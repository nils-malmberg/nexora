from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_owned_portfolio, require_csrf
from app.api.pagination import clamp_page_size, decode_cursor, encode_cursor
from app.config import settings
from app.domain.positions import (
    DuplicateTransactionError,
    PositionView,
    apply_transaction,
    compute_positions,
    compute_valuation,
    rebuild_lots,
)
from app.models import AuditEvent, Instrument, Portfolio, Transaction, User
from app.observability.metrics import transactions_created_total
from app.schemas.common import Page
from app.schemas.portfolios import PortfolioCreate, PortfolioOut, PortfolioUpdate
from app.schemas.transactions import (
    PositionOut,
    TransactionCreate,
    TransactionOut,
    TransactionReverseRequest,
    ValuationOut,
)

router = APIRouter(prefix="/api/v1/portfolios", tags=["portfolios"])

LOT_AFFECTING_TYPES = ("achat", "vente", "split")


def _position_out(view: PositionView) -> PositionOut:
    return PositionOut(
        instrument_id=view.instrument.id,
        symbol=view.instrument.symbol,
        name=view.instrument.name,
        quantity=view.quantity,
        average_unit_cost=view.average_unit_cost,
        currency=view.currency,
        price=view.price.price if view.price else None,
        price_as_of=view.price.as_of if view.price else None,
        market_value=view.market_value,
        freshness=view.freshness,
        matches_base_currency=view.matches_base_currency,
    )


@router.get("", response_model=list[PortfolioOut])
def list_portfolios(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[PortfolioOut]:
    portfolios = db.scalars(select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.created_at)).all()
    return [PortfolioOut.model_validate(p) for p in portfolios]


@router.post("", response_model=PortfolioOut, status_code=201)
def create_portfolio(
    payload: PortfolioCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> PortfolioOut:
    portfolio = Portfolio(user_id=user.id, name=payload.name, base_currency=payload.base_currency)
    db.add(portfolio)
    db.commit()
    return PortfolioOut.model_validate(portfolio)


@router.get("/{portfolio_id}", response_model=PortfolioOut)
def get_portfolio(
    portfolio_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> PortfolioOut:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    return PortfolioOut.model_validate(portfolio)


@router.patch("/{portfolio_id}", response_model=PortfolioOut)
def update_portfolio(
    portfolio_id: str,
    payload: PortfolioUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> PortfolioOut:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    if payload.name is not None:
        portfolio.name = payload.name
    db.commit()
    return PortfolioOut.model_validate(portfolio)


@router.delete("/{portfolio_id}", status_code=204)
def delete_portfolio(
    portfolio_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> None:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    db.add(
        AuditEvent(
            user_id=user.id,
            portfolio_id=portfolio.id,
            action="portfolio.delete",
            target_type="portfolio",
            target_id=portfolio.id,
        )
    )
    db.delete(portfolio)
    db.commit()


def _validate_instrument(db: Session, user: User, instrument_id: str | None) -> Instrument | None:
    if instrument_id is None:
        return None
    instrument = db.get(Instrument, instrument_id)
    if instrument is None or instrument.user_id != user.id:
        raise HTTPException(status_code=404, detail="instrument not found")
    return instrument


@router.get("/{portfolio_id}/transactions", response_model=Page[TransactionOut])
def list_transactions(
    portfolio_id: str,
    cursor: str | None = None,
    limit: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[TransactionOut]:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    page_size = clamp_page_size(limit, settings.default_page_size, settings.max_page_size)

    query = (
        select(Transaction)
        .where(Transaction.portfolio_id == portfolio.id)
        .order_by(Transaction.trade_date.desc(), Transaction.id.desc())
    )
    if cursor:
        cursor_key, cursor_id = decode_cursor(cursor)
        query = query.where(tuple_(Transaction.trade_date, Transaction.id) < tuple_(cursor_key, cursor_id))

    rows = list(db.scalars(query.limit(page_size + 1)).all())
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    next_cursor = encode_cursor(rows[-1].trade_date, rows[-1].id) if has_more and rows else None
    return Page(items=[TransactionOut.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.post("/{portfolio_id}/transactions", response_model=TransactionOut, status_code=201)
def create_transaction(
    portfolio_id: str,
    payload: TransactionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> TransactionOut:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    instrument = _validate_instrument(db, user, payload.instrument_id)

    try:
        tx = apply_transaction(db, portfolio, instrument, payload)
    except DuplicateTransactionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db.commit()
    transactions_created_total.labels(type=payload.type).inc()
    return TransactionOut.model_validate(tx)


@router.post("/{portfolio_id}/transactions/{transaction_id}/reverse", response_model=TransactionOut)
def reverse_transaction(
    portfolio_id: str,
    transaction_id: str,
    payload: TransactionReverseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> TransactionOut:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    tx = db.get(Transaction, transaction_id)
    if tx is None or tx.portfolio_id != portfolio.id:
        raise HTTPException(status_code=404, detail="transaction not found")
    if tx.reversed_at is not None:
        raise HTTPException(status_code=409, detail="transaction already reversed")

    tx.reversed_at = datetime.now(UTC)
    tx.reversal_reason = payload.reason
    db.add(
        AuditEvent(
            user_id=user.id,
            portfolio_id=portfolio.id,
            action="transaction.reverse",
            target_type="transaction",
            target_id=tx.id,
            event_metadata={"reason": payload.reason},
        )
    )

    if tx.instrument_id and tx.type in LOT_AFFECTING_TYPES:
        try:
            rebuild_lots(db, portfolio.id, tx.instrument_id)
        except ValueError as exc:
            db.rollback()
            raise HTTPException(
                status_code=422,
                detail=(
                    "cannot reverse: a later transaction depends on this one's effect "
                    f"({exc}); reverse the later transaction(s) first"
                ),
            ) from exc

    db.commit()
    return TransactionOut.model_validate(tx)


@router.get("/{portfolio_id}/positions", response_model=list[PositionOut])
def get_positions(
    portfolio_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[PositionOut]:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    return [_position_out(v) for v in compute_positions(db, portfolio)]


@router.get("/{portfolio_id}/valuation", response_model=ValuationOut)
def get_valuation(
    portfolio_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ValuationOut:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    position_views = compute_positions(db, portfolio)
    valuation = compute_valuation(db, portfolio, positions=position_views)
    positions = [_position_out(v) for v in position_views]
    return ValuationOut(
        base_currency=valuation.base_currency,
        cash=valuation.cash,
        cash_by_currency=valuation.cash_by_currency,
        positions_value=valuation.positions_value,
        total_value=valuation.total_value,
        unconverted_currencies=valuation.unconverted_currencies,
        has_missing_prices=valuation.has_missing_prices,
        positions=positions,
    )
