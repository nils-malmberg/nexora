"""Quant toolbox against textbook cases and invariants (no DB, no network)."""

from __future__ import annotations

import math
from decimal import Decimal

import numpy as np

from app.domain import quant


def _gbm(n=500, mu=0.0004, sigma=0.01, seed=1, s0=100.0):
    rng = np.random.default_rng(seed)
    r = rng.normal(mu, sigma, n)
    return list(s0 * np.exp(np.cumsum(r)))


# --- returns / risk ------------------------------------------------------------------


def test_return_stats_insufficient_data_is_explicit():
    stats = quant.return_stats([100, 101, 102])
    assert stats.has_sufficient_data is False
    assert stats.sharpe is None and stats.volatility_annualized is None


def test_return_stats_constant_growth_has_zero_volatility_and_known_cagr():
    values = [100 * (1.001**i) for i in range(300)]
    stats = quant.return_stats(values, periods_per_year=252)
    assert stats.has_sufficient_data
    assert stats.volatility_annualized == 0.0 or stats.volatility_annualized < 1e-9
    assert stats.max_drawdown == 0.0
    assert math.isclose(stats.total_return, 1.001**299 - 1, rel_tol=1e-9)
    assert stats.sharpe is None  # zero volatility: undefined rather than infinite
    assert stats.positive_period_share == 1.0


def test_return_stats_matches_numpy_on_random_series():
    values = _gbm()
    stats = quant.return_stats(values, periods_per_year=252, risk_free_rate=0.0)
    r = np.diff(values) / np.array(values[:-1])
    assert math.isclose(stats.volatility_annualized, r.std(ddof=1) * math.sqrt(252), rel_tol=1e-9)
    assert math.isclose(stats.sharpe, r.mean() * 252 / (r.std(ddof=1) * math.sqrt(252)), rel_tol=1e-9)
    assert -1 <= stats.max_drawdown <= 0
    assert stats.sortino is not None and stats.calmar is not None


def test_drawdown_series_known_case():
    dd = quant.drawdown_series([100, 120, 90, 100, 130, 65])
    assert dd[0] == 0.0 and dd[1] == 0.0
    assert math.isclose(dd[2], 90 / 120 - 1)
    assert math.isclose(min(dd), 65 / 130 - 1)


def test_value_at_risk_orderings():
    values = _gbm(n=1000, seed=7)
    var = quant.value_at_risk(values, confidence=0.95, horizon_periods=1)
    assert var.has_sufficient_data
    assert var.historical_var > 0
    assert var.historical_cvar >= var.historical_var  # expected shortfall is at least the quantile loss
    var10 = quant.value_at_risk(values, confidence=0.95, horizon_periods=10)
    assert math.isclose(var10.historical_var, var.historical_var * math.sqrt(10), rel_tol=1e-9)
    assert quant.value_at_risk(values[:10]).has_sufficient_data is False


def test_capm_recovers_beta_of_synthetic_relationship():
    rng = np.random.default_rng(3)
    rb = rng.normal(0.0003, 0.01, 800)
    ra = 0.0001 + 1.5 * rb + rng.normal(0, 0.001, 800)
    bench = list(100 * np.exp(np.cumsum(rb)))
    asset = list(100 * np.exp(np.cumsum(ra)))
    result = quant.capm(asset, bench)
    assert result.has_sufficient_data
    assert math.isclose(result.beta, 1.5, abs_tol=0.05)
    assert result.r_squared > 0.95
    assert result.tracking_error_annualized > 0


def test_correlation_matrix_is_symmetric_with_unit_diagonal():
    a = _gbm(seed=1)
    b = _gbm(seed=2)
    result = quant.correlation_matrix({"A": a, "B": b, "A2": [v * 2 for v in a]})
    assert result.has_sufficient_data
    m = result.matrix
    assert all(math.isclose(m[i][i], 1.0) for i in range(3))
    assert math.isclose(m[0][1], m[1][0])
    assert math.isclose(m[0][2], 1.0, abs_tol=1e-9)  # scaled copy: perfectly correlated
    assert quant.correlation_matrix({"A": a[:5], "B": b[:5]}).has_sufficient_data is False


def test_align_on_dates_keeps_only_common_dates_without_filling():
    common, aligned = quant.align_on_dates({"A": [(1, 10), (2, 11), (3, 12)], "B": [(2, 20), (3, 21), (4, 22)]})
    assert common == [2, 3]
    assert aligned == {"A": [11, 12], "B": [20, 21]}


# --- Markowitz --------------------------------------------------------------------------


def test_efficient_frontier_properties():
    series = {
        "A": _gbm(seed=11, mu=0.0005, sigma=0.012),
        "B": _gbm(seed=12, mu=0.0002, sigma=0.006),
        "C": _gbm(seed=13, mu=0.0004, sigma=0.02),
    }
    result = quant.efficient_frontier(series, points=10, current_weights=[0.5, 0.3, 0.2])
    assert result.has_sufficient_data
    for point in [result.min_variance, result.max_sharpe, *result.frontier]:
        assert math.isclose(sum(point.weights), 1.0, abs_tol=1e-6)
        assert all(w >= -1e-9 for w in point.weights)  # long-only
    # Minimum-variance point has the smallest volatility of everything computed
    # (up to the optimiser's numerical tolerance).
    tol = 1e-6
    assert result.min_variance.volatility <= min(p.volatility for p in result.frontier) + tol
    assert result.min_variance.volatility <= result.equal_weight.volatility + tol
    assert result.min_variance.volatility <= result.current.volatility + tol
    # The frontier is non-decreasing in expected return.
    rets = [p.expected_return for p in result.frontier]
    assert all(rets[i] <= rets[i + 1] + 1e-9 for i in range(len(rets) - 1))
    # Max-Sharpe point has the best Sharpe among frontier points.
    assert result.max_sharpe.sharpe >= max(p.sharpe for p in result.frontier if p.sharpe is not None) - 1e-6


def test_efficient_frontier_needs_two_assets_and_enough_history():
    assert quant.efficient_frontier({"A": _gbm()}).has_sufficient_data is False
    assert quant.efficient_frontier({"A": _gbm(n=20), "B": _gbm(n=20, seed=2)}).has_sufficient_data is False


# --- Monte Carlo ----------------------------------------------------------------


def test_monte_carlo_is_reproducible_and_ordered():
    values = _gbm(seed=5)
    a = quant.monte_carlo_gbm(values, horizon_periods=50, simulations=300, seed=9)
    b = quant.monte_carlo_gbm(values, horizon_periods=50, simulations=300, seed=9)
    assert a.has_sufficient_data and a.percentiles == b.percentiles
    assert a.percentiles["5"][0] == a.percentiles["95"][0] == values[-1]  # every path starts at the last value
    last = len(a.percentiles["50"]) - 1
    assert a.percentiles["5"][last] < a.percentiles["50"][last] < a.percentiles["95"][last]
    assert 0 <= a.probability_of_loss <= 1
    assert quant.monte_carlo_gbm(values, seed=1) != quant.monte_carlo_gbm(values, seed=2)


# --- extended indicators ---------------------------------------------------------


def test_bollinger_bands_bracket_the_middle_and_wait_for_window():
    closes = [Decimal(str(100 + math.sin(i / 3) * 5)) for i in range(40)]
    ext = quant.compute_extended_indicators(closes, bollinger_window=20, bollinger_k=2.0)
    assert ext.bollinger_middle[:19] == [None] * 19
    for u, m, lo in zip(ext.bollinger_upper[19:], ext.bollinger_middle[19:], ext.bollinger_lower[19:], strict=True):
        assert lo <= m <= u
    assert ext.atr == [None] * 40  # no highs/lows -> no ATR, never faked
    assert ext.obv == [None] * 40


def test_atr_stochastic_and_obv_with_ohlc():
    n = 30
    closes = [Decimal(100 + i) for i in range(n)]
    highs = [c + 2 for c in closes]
    lows = [c - 2 for c in closes]
    volumes = [Decimal(1000)] * n
    ext = quant.compute_extended_indicators(closes, highs, lows, volumes, atr_window=14, stochastic_window=14)
    assert ext.atr[12] is None and ext.atr[13] is not None
    assert all(a > 0 for a in ext.atr[13:])
    assert ext.stochastic_k[13] is not None and 0 <= ext.stochastic_k[13] <= 100
    assert ext.stochastic_d[15] is not None
    # monotonic rise: OBV accumulates every day's volume
    assert ext.obv[n - 1] == Decimal(1000 * (n - 1))
