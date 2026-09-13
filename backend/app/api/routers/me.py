from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_csrf
from app.models import (
    AuditEvent,
    ImportJob,
    Instrument,
    Notification,
    Portfolio,
    PredictionExperiment,
    PriceAlert,
    PricePoint,
    PrivateValuation,
    Transaction,
    User,
    UserSession,
    WatchlistItem,
)
from app.observability.metrics import account_deletions_total
from app.schemas.auth import UserOut
from app.schemas.imports import ImportJobSummaryOut
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
    watchlist_instrument_ids: list[str]
    import_jobs: list[ImportJobSummaryOut]
    prediction_experiments: list[dict]
    alerts: list[dict] = []
    notifications: list[dict] = []


class DeleteAccountRequest(BaseModel):
    password: str


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    reference_currency: str | None = Field(default=None, min_length=3, max_length=8)
    display_timezone: str | None = Field(default=None, max_length=64)


class SessionOut(BaseModel):
    id: str
    created_at: str
    last_seen_at: str
    user_agent: str | None
    current: bool


@router.get("/export", response_model=ExportOut)
def export_my_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExportOut:
    """specs/PRODUCT_SPEC.md: "Export des données utilisateur" — everything
    the user created plus the catalog rows their data references, nothing
    about any other user."""
    portfolios = db.scalars(select(Portfolio).where(Portfolio.user_id == user.id)).all()
    portfolio_ids = [p.id for p in portfolios]
    transactions = (
        db.scalars(select(Transaction).where(Transaction.portfolio_id.in_(portfolio_ids))).all()
        if portfolio_ids
        else []
    )
    watchlist = db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == user.id)).all()
    own_instruments = db.scalars(select(Instrument).where(Instrument.user_id == user.id)).all()
    referenced_ids = {t.instrument_id for t in transactions if t.instrument_id} | {w.instrument_id for w in watchlist}
    referenced_ids -= {i.id for i in own_instruments}
    referenced = db.scalars(select(Instrument).where(Instrument.id.in_(referenced_ids))).all() if referenced_ids else []
    instruments = [*own_instruments, *referenced]
    own_ids = [i.id for i in own_instruments]
    price_points = db.scalars(select(PricePoint).where(PricePoint.instrument_id.in_(own_ids))).all() if own_ids else []
    private_valuations = (
        db.scalars(select(PrivateValuation).where(PrivateValuation.instrument_id.in_(own_ids))).all() if own_ids else []
    )
    jobs = db.scalars(select(ImportJob).where(ImportJob.user_id == user.id)).all()
    experiments = db.scalars(select(PredictionExperiment).where(PredictionExperiment.user_id == user.id)).all()
    alerts = db.scalars(select(PriceAlert).where(PriceAlert.user_id == user.id)).all()
    notifications = db.scalars(select(Notification).where(Notification.user_id == user.id)).all()

    return ExportOut(
        user=UserOut.model_validate(user),
        portfolios=[PortfolioOut.model_validate(p) for p in portfolios],
        instruments=[InstrumentOut.from_model(i) for i in instruments],
        transactions=[TransactionOut.model_validate(t) for t in transactions],
        price_points=[PricePointOut.model_validate(p) for p in price_points],
        private_valuations=[PrivateValuationOut.model_validate(v) for v in private_valuations],
        watchlist_instrument_ids=[w.instrument_id for w in watchlist],
        import_jobs=[ImportJobSummaryOut.model_validate(j) for j in jobs],
        prediction_experiments=[
            {
                "id": e.id,
                "name": e.name,
                "instrument_id": e.instrument_id,
                "status": e.status,
                "config": e.config,
                "metrics": e.metrics,
                "dataset_hash": e.dataset_hash,
                "code_version": e.code_version,
                "trained_at": e.trained_at.isoformat() if e.trained_at else None,
            }
            for e in experiments
        ],
        alerts=[
            {
                "id": a.id,
                "instrument_id": a.instrument_id,
                "kind": a.kind,
                "threshold": str(a.threshold),
                "note": a.note,
                "active": a.active,
                "created_at": a.created_at.isoformat(),
                "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
            }
            for a in alerts
        ],
        notifications=[
            {
                "id": n.id,
                "instrument_id": n.instrument_id,
                "kind": n.kind,
                "title": n.title,
                "body": n.body,
                "created_at": n.created_at.isoformat(),
                "read_at": n.read_at.isoformat() if n.read_at else None,
            }
            for n in notifications
        ],
    )


@router.patch("", response_model=UserOut)
def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> UserOut:
    if payload.display_name is not None:
        user.display_name = payload.display_name or None
    if payload.reference_currency is not None:
        user.reference_currency = payload.reference_currency.upper()
    if payload.display_timezone is not None:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(payload.display_timezone)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=422, detail="unknown timezone") from exc
        user.display_timezone = payload.display_timezone
    db.commit()
    return UserOut.model_validate(user)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SessionOut]:
    from datetime import UTC, datetime

    from app.api.deps import get_current_session  # noqa: F401  (documentation: same mechanism)

    now = datetime.now(UTC)
    sessions = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > now)
        .order_by(UserSession.last_seen_at.desc())
    ).all()
    latest = sessions[0].id if sessions else None
    return [
        SessionOut(
            id=s.id,
            created_at=s.created_at.isoformat(),
            last_seen_at=s.last_seen_at.isoformat(),
            user_agent=s.user_agent,
            current=s.id == latest,
        )
        for s in sessions
    ]


@router.post("/sessions/revoke-others", status_code=204)
def revoke_other_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> None:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    sessions = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_seen_at.desc())
    ).all()
    for s in sessions[1:]:
        s.revoked_at = now
    db.add(AuditEvent(user_id=user.id, action="session.revoke_others", target_type="user", target_id=user.id))
    db.commit()


@router.delete("", status_code=204)
def delete_my_account(
    payload: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> None:
    """Requires re-authentication (current password). Cascades to every row
    owned by this user; shared catalog rows and the audit trail survive."""
    if not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=401, detail="incorrect password")

    db.add(AuditEvent(user_id=None, action="account.delete", target_type="user", target_id=user.id))
    db.delete(user)
    db.commit()
    account_deletions_total.inc()
