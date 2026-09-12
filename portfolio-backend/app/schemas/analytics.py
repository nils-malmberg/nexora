from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ValuationPointOut(BaseModel):
    as_of: datetime
    cash: Decimal
    positions_value: Decimal
    total_value: Decimal
    has_missing_prices: bool


class HistoryOut(BaseModel):
    base_currency: str
    points: list[ValuationPointOut]


class AllocationSliceOut(BaseModel):
    label: str
    value: Decimal
    share: Decimal


class AllocationOut(BaseModel):
    base_currency: str
    total_value: Decimal
    by_asset_class: list[AllocationSliceOut]
    by_instrument: list[AllocationSliceOut]
    by_currency: list[AllocationSliceOut]
    unconverted_currencies: list[str]


class RiskOut(BaseModel):
    has_sufficient_data: bool
    volatility_annualized: Decimal | None
    max_drawdown: Decimal | None
    observations: int
    method: str


class PerformanceOut(BaseModel):
    has_sufficient_data: bool
    start: datetime
    end: datetime
    base_currency: str
    twr: Decimal | None
    mwr: Decimal | None
    external_flow_count: int
    method: str


class IndicatorsOut(BaseModel):
    dates: list[datetime]
    prices: list[Decimal]
    sma: list[Decimal | None]
    ema: list[Decimal | None]
    rsi: list[Decimal | None]
    macd: list[Decimal | None]
    macd_signal: list[Decimal | None]
    sma_window: int
    ema_window: int
    rsi_window: int
    macd_fast: int
    macd_slow: int
    macd_signal_window: int
