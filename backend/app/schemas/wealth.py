"""Schemas for the consolidated view, realized gains, income, strategy
studies, rebased comparison and informational alerts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models import ALERT_KINDS
from app.schemas.analytics import AllocationSliceOut
from app.schemas.instruments import InstrumentOut
from app.schemas.quant import ReturnStatsOut

# --- consolidated wealth ----------------------------------------------------


class ConsolidatedPortfolioOut(BaseModel):
    id: str
    name: str
    base_currency: str
    total_value: Decimal
    total_value_reference: Decimal | None
    cash_reference: Decimal | None
    positions: int
    has_missing_prices: bool
    unconverted_currencies: list[str]
    fx_rate: Decimal | None
    fx_source: str | None


class ConsolidatedOut(BaseModel):
    reference_currency: str
    as_of: datetime
    total_value: Decimal
    cash: Decimal
    positions_value: Decimal
    portfolios: list[ConsolidatedPortfolioOut]
    by_portfolio: list[AllocationSliceOut]
    by_asset_class: list[AllocationSliceOut]
    by_instrument: list[AllocationSliceOut]
    by_currency: list[AllocationSliceOut]
    unconverted_currencies: list[str]
    has_missing_prices: bool


# --- realized gains and income ---------------------------------------------


class RealizedSaleOut(BaseModel):
    transaction_id: str
    instrument_id: str
    symbol: str
    name: str
    trade_date: datetime
    quantity: Decimal
    unit_price: Decimal
    currency: str
    proceeds: Decimal
    cost_basis: Decimal | None
    realized_pnl: Decimal | None
    realized_pnl_base: Decimal | None
    holding_days: int | None
    mixed_currency: bool
    fx_rate: Decimal | None
    fx_source: str | None


class RealizedTotalOut(BaseModel):
    key: str
    label: str
    sales: int
    realized_pnl_base: Decimal
    gains_base: Decimal
    losses_base: Decimal


class RealizedOut(BaseModel):
    base_currency: str
    year: int | None
    sales: list[RealizedSaleOut]
    by_year: list[RealizedTotalOut]
    by_instrument: list[RealizedTotalOut]
    total_realized_pnl_base: Decimal
    unconverted_currencies: list[str]
    mixed_currency_sales: int
    method: str


class IncomeRowOut(BaseModel):
    transaction_id: str
    trade_date: datetime
    type: str
    instrument_id: str | None
    symbol: str | None
    amount: Decimal
    currency: str
    amount_base: Decimal | None
    note: str | None


class IncomeTotalOut(BaseModel):
    key: str
    label: str
    income_base: Decimal
    fees_base: Decimal
    net_base: Decimal
    count: int


class IncomeOut(BaseModel):
    base_currency: str
    year: int | None
    rows: list[IncomeRowOut]
    by_year: list[IncomeTotalOut]
    by_month: list[IncomeTotalOut]
    by_instrument: list[IncomeTotalOut]
    total_income_base: Decimal
    total_fees_base: Decimal
    unconverted_currencies: list[str]
    method: str


# --- strategy study and comparison -----------------------------------------


class StrategyTradeOut(BaseModel):
    entry_date: datetime
    exit_date: datetime | None
    entry_price: float
    exit_price: float | None
    return_pct: float | None
    holding_days: int | None


class StrategyStudyOut(BaseModel):
    instrument_id: str
    symbol: str
    currency: str
    has_sufficient_data: bool
    observations: int
    rule: str
    params: dict
    fee_bps: float
    dates: list[datetime]
    strategy_equity: list[float]
    benchmark_equity: list[float]
    invested: list[int]
    trades: list[StrategyTradeOut]
    n_trades: int
    exposure_share: float | None
    win_rate: float | None
    strategy_stats: ReturnStatsOut | None
    benchmark_stats: ReturnStatsOut | None
    method: str
    disclaimer: str


class CompareSeriesOut(BaseModel):
    instrument: InstrumentOut
    values: list[float]
    total_return: float | None


class CompareOut(BaseModel):
    dates: list[datetime]
    base: float
    series: list[CompareSeriesOut]
    observations: int
    method: str


# --- alerts and notifications ------------------------------------------------


class AlertCreate(BaseModel):
    instrument_id: str = Field(min_length=1, max_length=32)
    kind: str
    threshold: Decimal = Field(gt=0)
    note: str | None = Field(default=None, max_length=200)

    @field_validator("kind")
    @classmethod
    def _kind(cls, value: str) -> str:
        if value not in ALERT_KINDS:
            raise ValueError(f"kind must be one of {', '.join(ALERT_KINDS)}")
        return value


class AlertOut(BaseModel):
    id: str
    instrument: InstrumentOut
    kind: str
    kind_label: str
    threshold: Decimal
    note: str | None
    active: bool
    created_at: datetime
    triggered_at: datetime | None
    last_evaluated_at: datetime | None
    last_value: Decimal | None


class NotificationOut(BaseModel):
    id: str
    instrument_id: str | None
    alert_id: str | None
    kind: str
    title: str
    body: str
    created_at: datetime
    read_at: datetime | None


class NotificationsOut(BaseModel):
    items: list[NotificationOut]
    unread: int


class MarkReadRequest(BaseModel):
    ids: list[str] | None = Field(default=None, max_length=200)  # None = everything
