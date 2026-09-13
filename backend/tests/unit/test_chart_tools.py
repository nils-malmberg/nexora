"""Chart tools on hand-made bars: known pivot arithmetic, Fibonacci levels,
Ichimoku shift, SAR trend flips and pattern detection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.domain import chart_tools as ct


def _dates(n):
    return [datetime(2025, 1, 6, tzinfo=UTC) + timedelta(days=i) for i in range(n)]


def test_pivot_points_classic_formula():
    d = _dates(30)
    highs = np.full(30, 110.0)
    lows = np.full(30, 90.0)
    closes = np.full(30, 100.0)
    day = ct.pivot_points(d, highs, lows, closes)[0]
    assert day.pivot == 100 and day.r1 == 110 and day.s1 == 90 and day.r2 == 120 and day.s2 == 80
    assert day.r3 == 130 and day.s3 == 70


def test_fibonacci_levels_follow_the_move_direction():
    d = _dates(40)
    up = np.concatenate([np.linspace(50, 100, 30), np.linspace(100, 80, 10)])
    fib = ct.fibonacci(d, up)
    assert fib.direction == "hausse" and fib.swing_low == 50 and fib.swing_high == 100
    levels = dict(fib.levels)
    assert levels[0.0] == 100 and levels[0.5] == 75 and levels[1.0] == 50
    assert fib.nearest_ratio == pytest.approx(0.382, abs=0.01)  # price 80 → retraced 40 %
    down = np.concatenate([np.linspace(100, 50, 30), np.linspace(50, 60, 10)])
    fib = ct.fibonacci(d, down)
    assert fib.direction == "baisse" and dict(fib.levels)[0.5] == 75
    assert ct.fibonacci(d, np.full(40, 10.0)) is None


def test_ichimoku_shifts_cloud_forward_and_reads_position():
    n = 120
    d = _dates(n)
    closes = np.linspace(100, 200, n)
    ich = ct.ichimoku(d, closes + 1, closes - 1, closes)
    # Kijun needs 26 bars (first value at index 25); the cloud is plotted 26 bars later.
    assert ich.senkou_a[50] is None and ich.senkou_a[51] is not None
    assert len(ich.future_dates) == 26 and all(x.weekday() < 5 for x in ich.future_dates)
    assert ich.chikou[-1] is None and ich.chikou[0] == closes[26]
    assert "au-dessus du nuage" in ich.reading and "élan positif" in ich.reading
    assert ct.ichimoku(d[:50], closes[:50], closes[:50], closes[:50]) is None


def test_parabolic_sar_flips_with_the_trend():
    closes = np.concatenate([np.linspace(100, 140, 40), np.linspace(140, 100, 40)])
    sar = ct.parabolic_sar(closes + 1, closes - 1, closes)
    assert sar.trend[20] == 1 and sar.values[20] < closes[20]
    assert sar.trend[-1] == -1 and sar.values[-1] > closes[-1]
    assert "baissière" in sar.reading


def test_candlestick_patterns_detected_on_textbook_shapes():
    d = _dates(12)
    # 6 falling candles, then a hammer, then a bullish engulfing.
    o = [110, 108, 106, 104, 102, 100, 99.0, 97, 95.5, 99, 100, 101]
    c = [108, 106, 104, 102, 100, 98, 100.0, 96, 99.5, 100, 101, 100.9]
    h = [110, 108, 106, 104, 102, 100, 100.1, 98, 100, 101, 102, 102]
    lo = [107, 105, 103, 101, 99, 97, 94.0, 95, 95, 98, 99, 99]
    patterns = ct.candlestick_patterns(d, o, h, lo, c)
    names = {p.name for p in patterns}
    assert "marteau" in names and "avalement_haussier" in names
    hammer = next(p for p in patterns if p.name == "marteau")
    assert hammer.index == 6 and hammer.direction == "haussier" and "mèche" in hammer.explanation
    doji = next(p for p in patterns if p.name == "doji")
    assert doji.index == 11


def test_bundle_without_ohlc_keeps_close_only_tools():
    d = _dates(60)
    closes = np.linspace(10, 20, 60)
    tools = ct.chart_tools(d, None, None, None, closes)
    assert tools.has_ohlc is False and tools.ichimoku is None and tools.sar is None and tools.pivots == []
    assert tools.fibonacci is not None and tools.patterns == []
