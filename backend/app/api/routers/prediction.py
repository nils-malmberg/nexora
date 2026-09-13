"""Experimental prediction module — specs/PREDICTION.md.

Gated by the `NEXORA_PREDICTION_ENABLED` kill switch (off by default): when
disabled every endpoint except `/status` answers 503 so the UI can explain
why. Experiments are user-owned, reproducible (config + dataset hash + code
version + seed), and evaluated by chronological walk-forward against a naive
benchmark. Nothing here is a price target, a signal, or advice.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_visible_instrument, require_csrf
from app.config import settings
from app.models import AuditEvent, Instrument, PredictionExperiment, User
from app.prediction import service as prediction_service
from app.prediction.engine import BASE_MODELS, CODE_VERSION
from app.schemas.prediction import ExperimentCreate, ExperimentOut, ExperimentSummaryOut, PredictionStatusOut

router = APIRouter(prefix="/api/v1/prediction", tags=["prediction"])

DISCLAIMER = (
    "Module expérimental et pédagogique. Les modèles sont entraînés sur des données passées et "
    "évalués en walk-forward ; leurs sorties sont des projections statistiques incertaines, jamais "
    "un objectif de prix, un signal d'achat/vente ni un conseil financier."
)


def _require_enabled() -> None:
    if not settings.prediction_enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "prediction module is disabled "
                "(set NEXORA_PREDICTION_ENABLED=true after reviewing specs/PREDICTION.md)"
            ),
        )


def _owned(experiment_id: str, db: Session, user: User) -> PredictionExperiment:
    exp = db.get(PredictionExperiment, experiment_id)
    if exp is None or exp.user_id != user.id:
        raise HTTPException(status_code=404, detail="experiment not found")
    return exp


def _summary(exp: PredictionExperiment, db: Session) -> ExperimentSummaryOut:
    instrument = db.get(Instrument, exp.instrument_id)
    return ExperimentSummaryOut(
        id=exp.id,
        instrument_id=exp.instrument_id,
        instrument_symbol=instrument.symbol if instrument else None,
        name=exp.name,
        status="running" if prediction_service.is_running(exp.id) else exp.status,
        code_version=exp.code_version,
        n_observations=exp.n_observations,
        trained_at=exp.trained_at,
        created_at=exp.created_at,
        error=exp.error,
        horizon=(exp.config or {}).get("horizon"),
    )


def _full(exp: PredictionExperiment, db: Session) -> ExperimentOut:
    base = _summary(exp, db)
    return ExperimentOut(
        **base.model_dump(),
        config=exp.config or {},
        dataset_hash=exp.dataset_hash,
        dataset_start=exp.dataset_start,
        dataset_end=exp.dataset_end,
        metrics=exp.metrics or {},
        folds=exp.folds or [],
        predictions=exp.predictions or [],
        latest_forecast=exp.latest_forecast,
        disclaimer=DISCLAIMER,
    )


@router.get("/status", response_model=PredictionStatusOut)
def prediction_status(user: User = Depends(get_current_user)) -> PredictionStatusOut:
    return PredictionStatusOut(
        enabled=settings.prediction_enabled,
        available_models=list(BASE_MODELS),
        min_observations=settings.prediction_min_observations,
        max_observations=settings.prediction_max_observations,
        disclaimer=DISCLAIMER,
    )


@router.get("/experiments", response_model=list[ExperimentSummaryOut])
def list_experiments(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ExperimentSummaryOut]:
    _require_enabled()
    rows = db.scalars(
        select(PredictionExperiment)
        .where(PredictionExperiment.user_id == user.id)
        .order_by(PredictionExperiment.created_at.desc())
    ).all()
    return [_summary(e, db) for e in rows]


@router.post("/experiments", response_model=ExperimentOut, status_code=201)
def create_experiment(
    payload: ExperimentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> ExperimentOut:
    _require_enabled()
    instrument = get_visible_instrument(payload.instrument_id, db, user)
    count = db.scalar(select(func.count(PredictionExperiment.id)).where(PredictionExperiment.user_id == user.id)) or 0
    if count >= settings.prediction_max_experiments_per_user:
        raise HTTPException(status_code=409, detail="experiment limit reached; delete older experiments first")
    exp = PredictionExperiment(
        user_id=user.id,
        instrument_id=instrument.id,
        name=payload.name,
        status="pending",
        config=payload.config.model_dump(),
        code_version=CODE_VERSION,
    )
    db.add(exp)
    db.add(AuditEvent(user_id=user.id, action="prediction.create", target_type="experiment", target_id=exp.id))
    db.commit()
    if payload.run_now:
        prediction_service.start_experiment(exp.id, background=settings.environment != "test", db=db)
        db.refresh(exp)
    return _full(exp, db)


@router.get("/experiments/{experiment_id}", response_model=ExperimentOut)
def get_experiment(
    experiment_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ExperimentOut:
    _require_enabled()
    exp = _owned(experiment_id, db, user)
    db.refresh(exp)
    return _full(exp, db)


@router.post("/experiments/{experiment_id}/run", response_model=ExperimentOut)
def rerun_experiment(
    experiment_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> ExperimentOut:
    _require_enabled()
    exp = _owned(experiment_id, db, user)
    if prediction_service.is_running(exp.id):
        raise HTTPException(status_code=409, detail="experiment is already running")
    exp.status = "pending"
    db.add(AuditEvent(user_id=user.id, action="prediction.run", target_type="experiment", target_id=exp.id))
    db.commit()
    prediction_service.start_experiment(exp.id, background=settings.environment != "test", db=db)
    db.refresh(exp)
    return _full(exp, db)


@router.delete("/experiments/{experiment_id}", status_code=204)
def delete_experiment(
    experiment_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> None:
    _require_enabled()
    exp = _owned(experiment_id, db, user)
    if prediction_service.is_running(exp.id):
        raise HTTPException(status_code=409, detail="experiment is running")
    db.delete(exp)
    db.commit()
