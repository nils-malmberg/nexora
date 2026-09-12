from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_csrf
from app.models import AuditEvent, Instrument, Portfolio, PricePoint, PrivateValuation, Transaction, User
from app.observability.metrics import account_deletions_total
from app.schemas.auth import UserOut
from app.schemas.instruments import InstrumentOut, PricePointOut, PrivateValuationOut
from app.schemas.portfolios import PortfolioOut
from app.schemas.transactions import TransactionOut
from app.security import verify_password

router = APIRouter(prefix="/api/v1/me", tags=["me"])


class ExportOut(BaseModel):
    user: UserOut
    portfolios: list[PortfolioOut]
    instruments: list[InstrumentOut]
    transactions: list[TransactionOut]
    price_points: list[PricePointOut]
    private_valuations: list[PrivateValuationOut]


class DeleteAccountRequest(BaseModel):
    password: str


@router.get("/export", response_model=ExportOut)
def export_my_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExportOut:
    """specs/PRODUCT_SPEC.md: "Export des données utilisateur" — everything
    the user themselves created, nothing about any other user."""
    portfolios = db.scalars(select(Portfolio).where(Portfolio.user_id == user.id)).all()
    portfolio_ids = [p.id for p in portfolios]
    instruments = db.scalars(select(Instrument).where(Instrument.user_id == user.id)).all()
    instrument_ids = [i.id for i in instruments]

    transactions = (
        db.scalars(select(Transaction).where(Transaction.portfolio_id.in_(portfolio_ids))).all()
        if portfolio_ids
        else []
    )
    price_points = (
        db.scalars(select(PricePoint).where(PricePoint.instrument_id.in_(instrument_ids))).all()
        if instrument_ids
        else []
    )
    private_valuations = (
        db.scalars(select(PrivateValuation).where(PrivateValuation.instrument_id.in_(instrument_ids))).all()
        if instrument_ids
        else []
    )

    return ExportOut(
        user=UserOut.model_validate(user),
        portfolios=[PortfolioOut.model_validate(p) for p in portfolios],
        instruments=[InstrumentOut.model_validate(i) for i in instruments],
        transactions=[TransactionOut.model_validate(t) for t in transactions],
        price_points=[PricePointOut.model_validate(p) for p in price_points],
        private_valuations=[PrivateValuationOut.model_validate(v) for v in private_valuations],
    )


@router.delete("", status_code=204)
def delete_my_account(
    payload: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> None:
    """Requires re-authentication (current password) — specs/UX_SPEC.md:
    "Confirmation pour suppression/export"; specs/API_SPEC.md: "DELETE /me
    (confirmation et réauthentification)". Cascades (DB-level `ondelete`) to
    every row owned by this user — portfolios, transactions, position lots,
    instruments, prices, private valuations, sessions. The audit trail row for
    this deletion itself keeps `user_id=None` rather than being cascaded away,
    so an incident investigation isn't erased by the deletion it might concern."""
    if not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=401, detail="incorrect password")

    db.add(AuditEvent(user_id=None, action="account.delete", target_type="user", target_id=user.id))
    db.delete(user)
    db.commit()
    account_deletions_total.inc()
