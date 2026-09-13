"""Schemas for the decision aid (instrument readings, market overview,
portfolio check-up) and the portfolio target allocation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models import ASSET_CLASSES
from app.schemas.instruments import InstrumentOut


class SignalOut(BaseModel):
    key: str
    family: str
    horizon: str
    label: str
    reading: str
    detail: str
    value: str | None
    strength: str
    evidence: str
    help_slug: str | None


class TallyOut(BaseModel):
    favorable: int
    defavorable: int
    neutre: int
    indisponible: int
    available: int


class HorizonOut(BaseModel):
    horizon: str
    label: str
    tally: TallyOut
    text: str


class FundamentalsStatusOut(BaseModel):
    status: str  # fresh | cached | stale | unavailable | not_supported | not_configured
    reason: str | None
    provider: str | None
    as_of: datetime | None
    source: str | None
    license_note: str | None
    env_var: str | None


class VerdictOut(BaseModel):
    horizon: str
    label: str
    orientation: str  # achat | vente | attendre
    orientation_label: str
    confidence: str
    text: str
    buy_case: list[str]
    sell_case: list[str]
    available: int


class LevelsOut(BaseModel):
    price: float
    atr: float | None
    stop_loss: float | None
    stop_loss_pct: float | None
    target: float | None
    target_pct: float | None
    risk_reward: float | None
    trailing_stop: float | None
    supports: list[float]
    resistances: list[float]
    high_52w: float | None
    low_52w: float | None
    position_size: int | None
    capital: float
    risk_pct: float
    risk_amount: float
    method: str


class HolderViewOut(BaseModel):
    held: bool
    entry_price: float | None
    pnl_pct: float | None
    orientation: str
    label: str
    text: str
    below_stop: bool | None


class DecisionAidOut(BaseModel):
    instrument: InstrumentOut
    as_of: datetime
    observations: int
    price_source: str | None
    signals: list[SignalOut]
    tally: TallyOut
    horizons: list[HorizonOut]
    overall: str
    verdicts: list[VerdictOut]
    orientation: str
    orientation_label: str
    orientation_confidence: str
    orientation_text: str
    levels: LevelsOut | None
    holder: HolderViewOut | None
    fundamentals: FundamentalsStatusOut
    prediction_available: bool
    news_last_7_days: int
    disclaimer: str


class OrientationStatsOut(BaseModel):
    orientation: str
    label: str
    count: int
    mean_return: float | None
    median_return: float | None
    hit_rate: float | None
    worst: float | None
    best: float | None


class TimelinePointOut(BaseModel):
    as_of: datetime
    orientation: str
    close: float


class PastValidationOut(BaseModel):
    instrument_id: str
    symbol: str
    horizon_days: int
    evaluations: int
    start: datetime | None
    end: datetime | None
    by_orientation: list[OrientationStatsOut]
    baseline_mean_return: float | None
    baseline_hit_rate: float | None
    timeline: list[TimelinePointOut]
    text: str
    method: str
    disclaimer: str


class DecisionOverviewEntry(BaseModel):
    instrument: InstrumentOut
    held: bool
    watched: bool
    orientation: str = "attendre"
    orientation_label: str = "Attendre / observer"
    orientation_confidence: str = "faible"
    observations: int
    tally: TallyOut
    trend: str  # reading of tendance_sma
    momentum: str  # reading of momentum_12_1
    rsi: str | None
    rsi_reading: str
    valuation: str  # reading of per, or "indisponible"
    overall: str


class DecisionOverviewOut(BaseModel):
    entries: list[DecisionOverviewEntry]
    fundamentals_configured: bool
    disclaimer: str


class AllocationShareOut(BaseModel):
    label: str
    share: float
    target: float | None
    drift: float | None


class PortfolioCheckupOut(BaseModel):
    portfolio_id: str
    base_currency: str
    as_of: datetime
    total_value: str
    signals: list[SignalOut]
    tally: TallyOut
    overall: str
    allocation: list[AllocationShareOut]
    has_targets: bool
    disclaimer: str


TARGET_KEYS = (*ASSET_CLASSES, "tresorerie")


class TargetAllocationUpdate(BaseModel):
    target_allocation: dict[str, float] | None = Field(default=None)

    @field_validator("target_allocation")
    @classmethod
    def _validate(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is None or value == {}:
            return None
        for key, share in value.items():
            if key not in TARGET_KEYS:
                raise ValueError(f"unknown allocation key {key!r}; expected one of {', '.join(TARGET_KEYS)}")
            if not 0 <= share <= 1:
                raise ValueError("each target share must be between 0 and 1")
        total = sum(value.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"target shares must sum to 1 (got {total:.3f})")
        return {k: round(v, 4) for k, v in value.items()}
