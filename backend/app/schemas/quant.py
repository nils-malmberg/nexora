from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ReturnStatsOut(BaseModel):
    subject: str
    label: str
    currency: str | None
    start: datetime | None
    end: datetime | None
    has_sufficient_data: bool
    observations: int
    periods_per_year: int
    risk_free_rate: float
    mean_return_annualized: float | None
    volatility_annualized: float | None
    downside_deviation_annualized: float | None
    sharpe: float | None
    sortino: float | None
    calmar: float | None
    max_drawdown: float | None
    skewness: float | None
    kurtosis_excess: float | None
    best_period: float | None
    worst_period: float | None
    positive_period_share: float | None
    total_return: float | None
    cagr: float | None
    method: str


class DrawdownPointOut(BaseModel):
    as_of: datetime
    value: float
    drawdown: float


class DrawdownOut(BaseModel):
    subject: str
    points: list[DrawdownPointOut]
    max_drawdown: float | None
    observations: int


class VarOut(BaseModel):
    subject: str
    has_sufficient_data: bool
    observations: int
    confidence: float
    horizon_periods: int
    historical_var: float | None
    historical_cvar: float | None
    gaussian_var: float | None
    cornish_fisher_var: float | None
    current_value: float | None
    currency: str | None
    method: str


class CapmOut(BaseModel):
    subject: str
    benchmark: str
    has_sufficient_data: bool
    observations: int
    beta: float | None
    alpha_annualized: float | None
    correlation: float | None
    r_squared: float | None
    tracking_error_annualized: float | None
    information_ratio: float | None
    risk_free_rate: float
    method: str


class CorrelationOut(BaseModel):
    labels: list[str]
    matrix: list[list[float | None]]
    observations: int
    has_sufficient_data: bool
    method: str = "corrélation de Pearson des rendements simples quotidiens, sur les seules dates communes"


class FrontierPointOut(BaseModel):
    expected_return: float
    volatility: float
    weights: list[float]
    sharpe: float | None


class FrontierOut(BaseModel):
    has_sufficient_data: bool
    labels: list[str]
    observations: int
    periods_per_year: int
    risk_free_rate: float
    expected_returns: list[float]
    volatilities: list[float]
    frontier: list[FrontierPointOut]
    min_variance: FrontierPointOut | None
    max_sharpe: FrontierPointOut | None
    equal_weight: FrontierPointOut | None
    current: FrontierPointOut | None
    method: str
    disclaimer: str


class MonteCarloOut(BaseModel):
    subject: str
    has_sufficient_data: bool
    observations: int
    horizon_periods: int
    simulations: int
    seed: int
    start_value: float | None
    currency: str | None
    drift_annualized: float | None
    volatility_annualized: float | None
    percentiles: dict[str, list[float]]
    terminal_percentiles: dict[str, float]
    probability_of_loss: float | None
    method: str
    disclaimer: str
