from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.domain.analytics import ValuationPoint, compute_indicators, risk_metrics, xirr, xnpv


def _dt(days: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=days)


def test_xnpv_zero_at_the_correct_rate():
    flows = [(_dt(0), Decimal("-1000")), (_dt(365), Decimal("1100"))]
    result = xnpv(Decimal("0.10"), flows)
    assert abs(result) < Decimal("0.01")


def test_xirr_matches_known_simple_rate():
    flows = [(_dt(0), Decimal("-1000")), (_dt(365), Decimal("1100"))]
    rate = xirr(flows)
    assert rate is not None
    assert abs(rate - Decimal("0.10")) < Decimal("0.001")


def test_xirr_with_multiple_flows():
    flows = [
        (_dt(0), Decimal("-1000")),
        (_dt(180), Decimal("-500")),
        (_dt(365), Decimal("1600")),
    ]
    rate = xirr(flows)
    assert rate is not None
    assert xnpv(rate, flows).copy_abs() < Decimal("1")


def test_xirr_returns_none_for_same_sign_flows():
    flows = [(_dt(0), Decimal("-1000")), (_dt(365), Decimal("-500"))]
    assert xirr(flows) is None


def test_xirr_returns_none_for_single_flow():
    assert xirr([(_dt(0), Decimal("-1000"))]) is None


def test_sma_none_until_window_fills():
    series = compute_indicators(
        dates=[_dt(i) for i in range(5)],
        prices=[Decimal(v) for v in [1, 2, 3, 4, 5]],
        sma_window=3,
        ema_window=3,
        rsi_window=3,
        macd_fast=2,
        macd_slow=3,
        macd_signal_window=2,
    )
    assert series.sma[0] is None
    assert series.sma[1] is None
    assert series.sma[2] == Decimal("2")
    assert series.sma[3] == Decimal("3")
    assert series.sma[4] == Decimal("4")


def test_rsi_is_100_when_only_gains():
    series = compute_indicators(
        dates=[_dt(i) for i in range(6)],
        prices=[Decimal(v) for v in [1, 2, 3, 4, 5, 6]],
        sma_window=3,
        ema_window=3,
        rsi_window=3,
        macd_fast=2,
        macd_slow=3,
        macd_signal_window=2,
    )
    assert series.rsi[-1] == Decimal("100")


def test_macd_signal_none_until_macd_values_accumulate():
    series = compute_indicators(
        dates=[_dt(i) for i in range(10)],
        prices=[Decimal(v) for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]],
        sma_window=3,
        ema_window=3,
        rsi_window=3,
        macd_fast=2,
        macd_slow=4,
        macd_signal_window=3,
    )
    assert series.macd[0] is None  # slow EMA (window 4) not filled yet
    assert any(m is not None for m in series.macd)
    assert series.macd_signal[-1] is not None


def test_risk_metrics_insufficient_data_below_three_points():
    history = [
        ValuationPoint(
            as_of=_dt(0),
            cash=Decimal("100"),
            positions_value=Decimal("0"),
            total_value=Decimal("100"),
            has_missing_prices=False,
        ),
        ValuationPoint(
            as_of=_dt(1),
            cash=Decimal("110"),
            positions_value=Decimal("0"),
            total_value=Decimal("110"),
            has_missing_prices=False,
        ),
    ]
    risk = risk_metrics(history)
    assert risk.has_sufficient_data is False
    assert risk.volatility_annualized is None
    assert risk.max_drawdown is None


def test_risk_metrics_max_drawdown():
    values = [100, 120, 90, 130, 80, 150]
    history = [
        ValuationPoint(
            as_of=_dt(i),
            cash=Decimal(v),
            positions_value=Decimal("0"),
            total_value=Decimal(v),
            has_missing_prices=False,
        )
        for i, v in enumerate(values)
    ]
    risk = risk_metrics(history)
    assert risk.has_sufficient_data is True
    # Worst peak-to-trough: 130 -> 80 = -38.46%
    assert risk.max_drawdown < Decimal("-0.38")
    assert risk.max_drawdown > Decimal("-0.39")
