from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.prediction.engine import BASE_MODELS


class ExperimentConfigIn(BaseModel):
    horizon: int = Field(default=5, ge=1, le=60, description="Périodes (jours de cotation) à l'avance")
    lags: int = Field(default=10, ge=1, le=60)
    windows: list[int] = Field(default=[5, 20, 60])
    models: list[str] = Field(default=["naive_last", "ridge", "random_forest", "gradient_boosting"])
    meta_model: str = Field(default="ridge_stacking")
    n_folds: int = Field(default=5, ge=2, le=12)
    min_train: int = Field(default=120, ge=60, le=2000)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    interval_confidence: float = Field(default=0.8, ge=0.5, le=0.99)

    @field_validator("models")
    @classmethod
    def _known_models(cls, value: list[str]) -> list[str]:
        unknown = [m for m in value if m not in BASE_MODELS]
        if unknown:
            raise ValueError(f"unknown models {unknown}; allowed: {list(BASE_MODELS)}")
        if not value:
            raise ValueError("at least one base model is required")
        return value

    @field_validator("meta_model")
    @classmethod
    def _known_meta(cls, value: str) -> str:
        if value not in ("ridge_stacking", "mean"):
            raise ValueError("meta_model must be 'ridge_stacking' or 'mean'")
        return value

    @field_validator("windows")
    @classmethod
    def _windows(cls, value: list[int]) -> list[int]:
        cleaned = sorted({int(w) for w in value if 2 <= int(w) <= 250})
        if not cleaned:
            raise ValueError("at least one window between 2 and 250 is required")
        return cleaned[:6]


class ExperimentCreate(BaseModel):
    instrument_id: str
    name: str = Field(min_length=1, max_length=120)
    config: ExperimentConfigIn = Field(default_factory=ExperimentConfigIn)
    run_now: bool = True


class ExperimentSummaryOut(BaseModel):
    id: str
    instrument_id: str
    instrument_symbol: str | None
    name: str
    status: str
    code_version: str
    n_observations: int
    trained_at: datetime | None
    created_at: datetime
    error: str | None
    horizon: int | None


class ExperimentOut(ExperimentSummaryOut):
    config: dict
    dataset_hash: str | None
    dataset_start: datetime | None
    dataset_end: datetime | None
    metrics: dict
    folds: list
    predictions: list
    latest_forecast: dict | None
    disclaimer: str


class PredictionStatusOut(BaseModel):
    enabled: bool
    available_models: list[str]
    min_observations: int
    max_observations: int
    disclaimer: str
