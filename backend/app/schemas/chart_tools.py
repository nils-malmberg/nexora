from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IchimokuOut(BaseModel):
    tenkan: list[float | None]
    kijun: list[float | None]
    senkou_a: list[float | None]
    senkou_b: list[float | None]
    chikou: list[float | None]
    future_dates: list[datetime]
    future_senkou_a: list[float | None]
    future_senkou_b: list[float | None]
    reading: str


class SarOut(BaseModel):
    values: list[float | None]
    trend: list[int]
    reading: str


class PivotSetOut(BaseModel):
    period: str
    based_on: str
    pivot: float
    r1: float
    r2: float
    r3: float
    s1: float
    s2: float
    s3: float


class FibonacciOut(BaseModel):
    swing_high: float
    swing_high_date: datetime
    swing_low: float
    swing_low_date: datetime
    direction: str
    levels: list[tuple[float, float]]
    nearest_ratio: float | None
    reading: str


class PatternOut(BaseModel):
    index: int
    as_of: datetime
    name: str
    direction: str
    explanation: str


class ChartToolsOut(BaseModel):
    instrument_id: str
    dates: list[datetime]
    has_ohlc: bool
    ichimoku: IchimokuOut | None
    sar: SarOut | None
    pivots: list[PivotSetOut]
    fibonacci: FibonacciOut | None
    supports: list[float]
    resistances: list[float]
    patterns: list[PatternOut]
    method: str
