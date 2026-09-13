"""Runs prediction experiments: loads the instrument's daily series, hands
it to the pure engine, persists metrics/predictions/forecast. Training runs
in a background thread (a few seconds for daily data) so the request returns
immediately with a `running` status the UI polls. The module is gated by
`NEXORA_PREDICTION_ENABLED` (kill switch, off by default)."""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.market import service as market_service
from app.models import Instrument, OhlcBar, PredictionExperiment, PricePoint
from app.observability.logging import get_logger, log_event
from app.observability.metrics import prediction_runs_total, prediction_training_seconds
from app.prediction.engine import CODE_VERSION, ExperimentConfig, build_dataset, dataset_fingerprint, walk_forward

logger = get_logger(__name__)

_running: set[str] = set()
_lock = threading.Lock()


def load_series(db: Session, instrument: Instrument, max_days: int | None = None) -> tuple[list[datetime], list[float]]:
    """Daily closes (bars), falling back to one price point per day. For a
    catalog instrument the stored history is topped up first (cache-first,
    at most one provider call)."""
    now = datetime.now(UTC)
    if instrument.user_id is None and instrument.provider not in (None, "manual", "null"):
        market_service.get_history(db, instrument, now - timedelta(days=max_days or 365 * 5), now)
    bars = db.scalars(select(OhlcBar).where(OhlcBar.instrument_id == instrument.id).order_by(OhlcBar.as_of)).all()
    if bars:
        dates = [b.as_of for b in bars]
        closes = [float(b.close) for b in bars]
    else:
        by_day: dict = {}
        for p in db.scalars(
            select(PricePoint).where(PricePoint.instrument_id == instrument.id).order_by(PricePoint.as_of)
        ):
            by_day[p.as_of.date()] = p
        ordered = [by_day[d] for d in sorted(by_day)]
        dates = [p.as_of for p in ordered]
        closes = [float(p.price) for p in ordered]
    limit = settings.prediction_max_observations
    if len(closes) > limit:
        dates, closes = dates[-limit:], closes[-limit:]
    return dates, closes


def run_experiment_sync(db: Session, experiment: PredictionExperiment) -> PredictionExperiment:
    started = time.monotonic()
    experiment.status = "running"
    experiment.error = None
    db.commit()
    try:
        instrument = db.get(Instrument, experiment.instrument_id)
        if instrument is None:
            raise ValueError("instrument not found")
        cfg = ExperimentConfig.from_dict(experiment.config or {})
        dates, closes = load_series(db, instrument)
        if len(closes) < settings.prediction_min_observations:
            raise ValueError(
                f"insufficient history: {len(closes)} daily observations, "
                f"need at least {settings.prediction_min_observations}"
            )
        ds = build_dataset(dates, closes, cfg)
        result = walk_forward(ds, cfg, [d.isoformat() for d in dates])
        experiment.dataset_hash = dataset_fingerprint(dates, closes)
        experiment.dataset_start = dates[0]
        experiment.dataset_end = dates[-1]
        experiment.n_observations = len(closes)
        experiment.code_version = CODE_VERSION
        experiment.config = result.config
        if not result.ok:
            experiment.status = "failed"
            experiment.error = result.reason
            prediction_runs_total.labels(outcome="insufficient_data").inc()
        else:
            experiment.metrics = {
                "models": result.metrics,
                "meta_weights": result.meta_weights,
                "feature_names": result.feature_names,
            }
            experiment.folds = [f.__dict__ for f in result.folds]
            experiment.predictions = result.predictions
            experiment.latest_forecast = result.latest_forecast
            experiment.status = "completed"
            experiment.trained_at = datetime.now(UTC)
            prediction_runs_total.labels(outcome="completed").inc()
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, never swallowed silently
        experiment.status = "failed"
        experiment.error = f"{exc.__class__.__name__}: {exc}"[:2000]
        prediction_runs_total.labels(outcome="failed").inc()
        log_event(
            logger, logging.WARNING, "prediction experiment failed", experiment_id=experiment.id, error=str(exc)[:200]
        )
    finally:
        prediction_training_seconds.observe(time.monotonic() - started)
    db.commit()
    return experiment


def _run_in_thread(experiment_id: str, db: Session | None = None) -> None:
    own_session = db is None
    db = db or SessionLocal()
    try:
        experiment = db.get(PredictionExperiment, experiment_id)
        if experiment is not None:
            run_experiment_sync(db, experiment)
    finally:
        if own_session:
            db.close()
        with _lock:
            _running.discard(experiment_id)


def start_experiment(experiment_id: str, *, background: bool = True, db: Session | None = None) -> None:
    """Background (a daemon thread with its own session) by default; the
    synchronous path reuses the caller's session — used by tests, where the
    database is an in-memory SQLite visible only through that session."""
    with _lock:
        if experiment_id in _running:
            return
        _running.add(experiment_id)
    if background:
        threading.Thread(
            target=_run_in_thread, args=(experiment_id,), daemon=True, name=f"pred-{experiment_id[:8]}"
        ).start()
    else:
        _run_in_thread(experiment_id, db)


def is_running(experiment_id: str) -> bool:
    with _lock:
        return experiment_id in _running
