"""Quantitative toolbox: extended technical indicators, return statistics
(Sharpe, Sortino, Calmar, skew/kurtosis), Value-at-Risk (historical,
Gaussian, Cornish-Fisher), CAPM beta/alpha, correlation, Markowitz
mean-variance frontier, and Monte Carlo (GBM) simulation.

All functions are pure (no DB) and take plain sequences, so they are unit
testable against textbook examples. Statistics are floats (they are not
money); money stays Decimal upstream. Every function returns `None` / an
explicit "insufficient data" marker instead of a number when the sample is
too small — the theory behind each measure, and its limits, is documented for
users in app/education_content.py. Nothing here is a recommendation: these
describe the past or simulate assumptions, they never say buy or sell.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np

TRADING_DAYS = 252
_Q = Decimal("0.000001")


def _f(values) -> np.ndarray:
    return np.array([float(v) for v in values], dtype=float)


def _d(value: float | None) -> Decimal | None:
    if value is None or not math.isfinite(value):
        return None
    return Decimal(str(round(value, 8))).quantize(_Q)


# ---------------------------------------------------------------------------
# Extended technical indicators
# ---------------------------------------------------------------------------


@dataclass
class ExtendedIndicators:
    bollinger_upper: list[Decimal | None]
    bollinger_middle: list[Decimal | None]
    bollinger_lower: list[Decimal | None]
    atr: list[Decimal | None]
    stochastic_k: list[Decimal | None]
    stochastic_d: list[Decimal | None]
    obv: list[Decimal | None]


def rolling_mean_std(values: np.ndarray, window: int) -> tuple[list[float | None], list[float | None]]:
    means: list[float | None] = []
    stds: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < window:
            means.append(None)
            stds.append(None)
            continue
        seg = values[i + 1 - window : i + 1]
        means.append(float(seg.mean()))
        stds.append(float(seg.std(ddof=0)))
    return means, stds


def compute_extended_indicators(
    closes,
    highs=None,
    lows=None,
    volumes=None,
    *,
    bollinger_window: int = 20,
    bollinger_k: float = 2.0,
    atr_window: int = 14,
    stochastic_window: int = 14,
    stochastic_smooth: int = 3,
) -> ExtendedIndicators:
    c = _f(closes)
    n = len(c)
    means, stds = rolling_mean_std(c, bollinger_window)
    upper = [_d(m + bollinger_k * s) if m is not None else None for m, s in zip(means, stds, strict=True)]
    middle = [_d(m) if m is not None else None for m in means]
    lower = [_d(m - bollinger_k * s) if m is not None else None for m, s in zip(means, stds, strict=True)]

    have_hl = highs is not None and lows is not None and len(highs) == n and all(h is not None for h in highs)
    atr: list[Decimal | None] = [None] * n
    k_line: list[Decimal | None] = [None] * n
    d_line: list[Decimal | None] = [None] * n
    if have_hl and n:
        h, low = _f(highs), _f(lows)
        tr = np.empty(n)
        tr[0] = h[0] - low[0]
        for i in range(1, n):
            tr[i] = max(h[i] - low[i], abs(h[i] - c[i - 1]), abs(low[i] - c[i - 1]))
        # Wilder's smoothing, seeded by the simple average of the first window.
        if n >= atr_window:
            value = float(tr[:atr_window].mean())
            atr[atr_window - 1] = _d(value)
            for i in range(atr_window, n):
                value = (value * (atr_window - 1) + tr[i]) / atr_window
                atr[i] = _d(value)
        raw_k: list[float | None] = []
        for i in range(n):
            if i + 1 < stochastic_window:
                raw_k.append(None)
                continue
            hh = h[i + 1 - stochastic_window : i + 1].max()
            ll = low[i + 1 - stochastic_window : i + 1].min()
            raw_k.append(50.0 if hh == ll else (c[i] - ll) / (hh - ll) * 100.0)
        for i in range(n):
            k_line[i] = _d(raw_k[i]) if raw_k[i] is not None else None
            window = [v for v in raw_k[max(0, i + 1 - stochastic_smooth) : i + 1] if v is not None]
            if raw_k[i] is not None and len(window) == stochastic_smooth:
                d_line[i] = _d(sum(window) / stochastic_smooth)

    obv: list[Decimal | None] = [None] * n
    if volumes is not None and len(volumes) == n and n and all(v is not None for v in volumes):
        v = _f(volumes)
        running = 0.0
        obv[0] = _d(0.0)
        for i in range(1, n):
            if c[i] > c[i - 1]:
                running += v[i]
            elif c[i] < c[i - 1]:
                running -= v[i]
            obv[i] = _d(running)

    return ExtendedIndicators(
        bollinger_upper=upper,
        bollinger_middle=middle,
        bollinger_lower=lower,
        atr=atr,
        stochastic_k=k_line,
        stochastic_d=d_line,
        obv=obv,
    )


# ---------------------------------------------------------------------------
# Returns and risk statistics
# ---------------------------------------------------------------------------


def simple_returns(values) -> np.ndarray:
    v = _f(values)
    if len(v) < 2:
        return np.array([], dtype=float)
    prev = v[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        r = (v[1:] - prev) / prev
    return r[np.isfinite(r)]


def log_returns(values) -> np.ndarray:
    v = _f(values)
    if len(v) < 2:
        return np.array([], dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.log(v[1:] / v[:-1])
    return r[np.isfinite(r)]


def drawdown_series(values) -> list[float]:
    v = _f(values)
    if len(v) == 0:
        return []
    peaks = np.maximum.accumulate(v)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peaks > 0, v / peaks - 1.0, 0.0)
    return [float(x) for x in dd]


@dataclass
class ReturnStats:
    has_sufficient_data: bool
    observations: int
    periods_per_year: int
    mean_return_annualized: float | None = None
    volatility_annualized: float | None = None
    downside_deviation_annualized: float | None = None
    sharpe: float | None = None
    sortino: float | None = None
    calmar: float | None = None
    max_drawdown: float | None = None
    skewness: float | None = None
    kurtosis_excess: float | None = None
    best_period: float | None = None
    worst_period: float | None = None
    positive_period_share: float | None = None
    total_return: float | None = None
    cagr: float | None = None
    risk_free_rate: float = 0.0
    method: str = (
        "rendements simples quotidiens ; annualisation par √(périodes par an) pour la volatilité et ×périodes "
        "pour la moyenne ; taux sans risque tel que fourni"
    )


def return_stats(
    values, *, periods_per_year: int = TRADING_DAYS, risk_free_rate: float = 0.0, min_obs: int = 20
) -> ReturnStats:
    r = simple_returns(values)
    n = len(r)
    if n < min_obs:
        return ReturnStats(
            has_sufficient_data=False, observations=n, periods_per_year=periods_per_year, risk_free_rate=risk_free_rate
        )
    mean = float(r.mean())
    vol = float(r.std(ddof=1))
    if vol < 1e-12:
        vol = 0.0  # a constant series: undefined ratios rather than astronomically large ones
    rf_period = (1 + risk_free_rate) ** (1 / periods_per_year) - 1
    excess = r - rf_period
    downside = np.minimum(excess, 0.0)
    dd_dev = float(math.sqrt((downside**2).mean()))
    if dd_dev < 1e-12:
        dd_dev = 0.0
    mdd = min(drawdown_series(values)) if len(values) else None
    ann_mean = mean * periods_per_year
    ann_vol = vol * math.sqrt(periods_per_year)
    ann_dd = dd_dev * math.sqrt(periods_per_year)
    sharpe = (float(excess.mean()) * periods_per_year) / ann_vol if ann_vol > 0 else None
    sortino = (float(excess.mean()) * periods_per_year) / ann_dd if ann_dd > 0 else None
    v = _f(values)
    total = float(v[-1] / v[0] - 1.0) if v[0] > 0 else None
    years = n / periods_per_year
    cagr = float((v[-1] / v[0]) ** (1 / years) - 1.0) if v[0] > 0 and years > 0 and v[-1] > 0 else None
    calmar = (cagr / abs(mdd)) if cagr is not None and mdd is not None and mdd < 0 else None
    centered = r - mean
    m2 = float((centered**2).mean())
    skew = float((centered**3).mean() / m2**1.5) if m2 > 0 else None
    kurt = float((centered**4).mean() / m2**2 - 3.0) if m2 > 0 else None
    return ReturnStats(
        has_sufficient_data=True,
        observations=n,
        periods_per_year=periods_per_year,
        mean_return_annualized=ann_mean,
        volatility_annualized=ann_vol,
        downside_deviation_annualized=ann_dd,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_drawdown=mdd,
        skewness=skew,
        kurtosis_excess=kurt,
        best_period=float(r.max()),
        worst_period=float(r.min()),
        positive_period_share=float((r > 0).mean()),
        total_return=total,
        cagr=cagr,
        risk_free_rate=risk_free_rate,
    )


@dataclass
class VarResult:
    has_sufficient_data: bool
    observations: int
    confidence: float
    horizon_periods: int
    historical_var: float | None = None
    historical_cvar: float | None = None
    gaussian_var: float | None = None
    cornish_fisher_var: float | None = None
    method: str = (
        "quantiles de perte des rendements de période, mis à l'échelle par √horizon ; historique = quantile "
        "empirique, gaussienne = μ + z·σ, Cornish-Fisher = z corrigé de l'asymétrie et de l'aplatissement"
    )


def _norm_ppf(p: float) -> float:
    from scipy.stats import norm

    return float(norm.ppf(p))


def value_at_risk(values, *, confidence: float = 0.95, horizon_periods: int = 1, min_obs: int = 30) -> VarResult:
    """Returns losses as positive fractions of the current value (e.g. 0.031
    = a 3.1 % loss at the given confidence)."""
    r = simple_returns(values)
    n = len(r)
    if n < min_obs:
        return VarResult(False, n, confidence, horizon_periods)
    alpha = 1 - confidence
    scale = math.sqrt(horizon_periods)
    q = float(np.quantile(r, alpha))
    tail = r[r <= q]
    hist_var = -q * scale
    hist_cvar = -float(tail.mean()) * scale if len(tail) else None
    mu, sigma = float(r.mean()), float(r.std(ddof=1))
    z = _norm_ppf(alpha)
    gauss = -(mu + z * sigma) * scale
    centered = r - mu
    m2 = float((centered**2).mean())
    skew = float((centered**3).mean() / m2**1.5) if m2 > 0 else 0.0
    kurt = float((centered**4).mean() / m2**2 - 3.0) if m2 > 0 else 0.0
    z_cf = z + (z**2 - 1) * skew / 6 + (z**3 - 3 * z) * kurt / 24 - (2 * z**3 - 5 * z) * skew**2 / 36
    cf = -(mu + z_cf * sigma) * scale
    return VarResult(True, n, confidence, horizon_periods, hist_var, hist_cvar, gauss, cf)


@dataclass
class CapmResult:
    has_sufficient_data: bool
    observations: int
    beta: float | None = None
    alpha_annualized: float | None = None
    correlation: float | None = None
    r_squared: float | None = None
    tracking_error_annualized: float | None = None
    information_ratio: float | None = None
    method: str = (
        "moindres carrés des rendements excédentaires de l'actif sur ceux du benchmark (MEDAF) ; alpha annualisé"
    )


def capm(
    asset_values,
    benchmark_values,
    *,
    periods_per_year: int = TRADING_DAYS,
    risk_free_rate: float = 0.0,
    min_obs: int = 30,
) -> CapmResult:
    ra, rb = simple_returns(asset_values), simple_returns(benchmark_values)
    n = min(len(ra), len(rb))
    if n < min_obs:
        return CapmResult(False, n)
    ra, rb = ra[-n:], rb[-n:]
    rf = (1 + risk_free_rate) ** (1 / periods_per_year) - 1
    ea, eb = ra - rf, rb - rf
    var_b = float(eb.var(ddof=1))
    if var_b <= 0:
        return CapmResult(False, n)
    cov = float(np.cov(ea, eb, ddof=1)[0, 1])
    beta = cov / var_b
    alpha = float(ea.mean() - beta * eb.mean()) * periods_per_year
    corr = float(np.corrcoef(ea, eb)[0, 1])
    diff = ra - rb
    te = float(diff.std(ddof=1)) * math.sqrt(periods_per_year)
    ir = (float(diff.mean()) * periods_per_year / te) if te > 0 else None
    return CapmResult(True, n, beta, alpha, corr, corr**2, te, ir)


@dataclass
class CorrelationResult:
    labels: list[str]
    matrix: list[list[float | None]]
    observations: int
    has_sufficient_data: bool


def correlation_matrix(series: dict[str, list], *, min_obs: int = 30) -> CorrelationResult:
    """Pearson correlation of aligned period returns. Callers align the
    series on common dates first (see analytics router)."""
    labels = list(series)
    returns = {k: simple_returns(v) for k, v in series.items()}
    n = min((len(r) for r in returns.values()), default=0)
    if n < min_obs or len(labels) < 2:
        return CorrelationResult(labels, [[None] * len(labels) for _ in labels], n, False)
    m = np.vstack([returns[k][-n:] for k in labels])
    corr = np.corrcoef(m)
    matrix = [
        [(float(corr[i, j]) if math.isfinite(corr[i, j]) else None) for j in range(len(labels))]
        for i in range(len(labels))
    ]
    return CorrelationResult(labels, matrix, n, True)


# ---------------------------------------------------------------------------
# Markowitz mean-variance frontier (long-only, fully invested)
# ---------------------------------------------------------------------------


@dataclass
class FrontierPoint:
    expected_return: float
    volatility: float
    weights: list[float]
    sharpe: float | None = None


@dataclass
class FrontierResult:
    has_sufficient_data: bool
    labels: list[str]
    observations: int
    periods_per_year: int
    risk_free_rate: float
    expected_returns: list[float] = field(default_factory=list)
    volatilities: list[float] = field(default_factory=list)
    frontier: list[FrontierPoint] = field(default_factory=list)
    min_variance: FrontierPoint | None = None
    max_sharpe: FrontierPoint | None = None
    equal_weight: FrontierPoint | None = None
    current: FrontierPoint | None = None
    method: str = (
        "moyenne et covariance empiriques des rendements quotidiens, annualisées ; minimisation quadratique "
        "(SLSQP) sous contraintes poids ≥ 0 et Σ poids = 1 (long seulement, entièrement investi, sans coûts). "
        "Les entrées sont des estimations historiques, très sensibles à l'échantillon — pas des prévisions."
    )


def _portfolio_stats(w: np.ndarray, mu: np.ndarray, cov: np.ndarray, rf: float) -> tuple[float, float, float | None]:
    ret = float(w @ mu)
    var = float(w @ cov @ w)
    vol = math.sqrt(max(var, 0.0))
    sharpe = (ret - rf) / vol if vol > 0 else None
    return ret, vol, sharpe


def efficient_frontier(
    series: dict[str, list],
    *,
    periods_per_year: int = TRADING_DAYS,
    risk_free_rate: float = 0.0,
    points: int = 25,
    current_weights: list[float] | None = None,
    min_obs: int = 60,
) -> FrontierResult:
    from scipy.optimize import minimize

    labels = list(series)
    k = len(labels)
    returns = {lab: simple_returns(v) for lab, v in series.items()}
    n = min((len(r) for r in returns.values()), default=0)
    if n < min_obs or k < 2:
        return FrontierResult(False, labels, n, periods_per_year, risk_free_rate)
    m = np.vstack([returns[lab][-n:] for lab in labels])
    mu = m.mean(axis=1) * periods_per_year
    cov = np.cov(m, ddof=1) * periods_per_year
    bounds = [(0.0, 1.0)] * k
    budget = {"type": "eq", "fun": lambda w: float(w.sum() - 1.0)}
    w0 = np.full(k, 1.0 / k)

    def _solve(objective, extra=()):
        res = minimize(
            objective, w0, method="SLSQP", bounds=bounds, constraints=[budget, *extra], options={"maxiter": 500}
        )
        w = np.clip(res.x, 0, 1)
        return w / w.sum()

    def _point(w: np.ndarray) -> FrontierPoint:
        ret, vol, sh = _portfolio_stats(w, mu, cov, risk_free_rate)
        return FrontierPoint(ret, vol, [float(x) for x in w], sh)

    w_min = _solve(lambda w: float(w @ cov @ w))
    w_sharpe = _solve(lambda w: -(_portfolio_stats(w, mu, cov, risk_free_rate)[2] or -1e9))
    min_var, max_sharpe = _point(w_min), _point(w_sharpe)

    frontier: list[FrontierPoint] = []
    lo, hi = min_var.expected_return, float(mu.max())
    if hi > lo:
        for target in np.linspace(lo, hi, points):
            w = _solve(lambda w: float(w @ cov @ w), [{"type": "eq", "fun": lambda w, t=target: float(w @ mu - t)}])
            frontier.append(_point(w))
    else:
        frontier.append(min_var)

    equal = _point(w0)
    current = None
    if current_weights is not None and len(current_weights) == k and sum(current_weights) > 0:
        cw = np.array(current_weights, dtype=float)
        current = _point(cw / cw.sum())

    return FrontierResult(
        True,
        labels,
        n,
        periods_per_year,
        risk_free_rate,
        [float(x) for x in mu],
        [float(math.sqrt(cov[i, i])) for i in range(k)],
        frontier,
        min_var,
        max_sharpe,
        equal,
        current,
    )


# ---------------------------------------------------------------------------
# Monte Carlo (geometric Brownian motion, calibrated on history)
# ---------------------------------------------------------------------------


@dataclass
class MonteCarloResult:
    has_sufficient_data: bool
    observations: int
    horizon_periods: int
    simulations: int
    seed: int
    drift_annualized: float | None = None
    volatility_annualized: float | None = None
    percentiles: dict[str, list[float]] = field(default_factory=dict)
    terminal_percentiles: dict[str, float] = field(default_factory=dict)
    probability_of_loss: float | None = None
    method: str = (
        "mouvement brownien géométrique, dérive et volatilité estimées sur les log-rendements historiques ; "
        "trajectoires tirées au hasard sous cette hypothèse (rendements normaux et indépendants) — une "
        "illustration de la dispersion, pas une prévision ; les rendements réels ont des queues épaisses et "
        "des regroupements de volatilité que le modèle ignore."
    )


def monte_carlo_gbm(
    values,
    *,
    horizon_periods: int = 252,
    simulations: int = 2000,
    seed: int = 42,
    periods_per_year: int = TRADING_DAYS,
    start_value: float | None = None,
    min_obs: int = 60,
    percentile_levels=(5, 25, 50, 75, 95),
) -> MonteCarloResult:
    lr = log_returns(values)
    n = len(lr)
    if n < min_obs:
        return MonteCarloResult(False, n, horizon_periods, simulations, seed)
    mu, sigma = float(lr.mean()), float(lr.std(ddof=1))
    s0 = float(start_value if start_value is not None else _f(values)[-1])
    rng = np.random.default_rng(seed)
    shocks = rng.standard_normal((simulations, horizon_periods))
    steps = (mu - 0.5 * sigma**2) + sigma * shocks
    paths = s0 * np.exp(np.cumsum(steps, axis=1))
    paths = np.hstack([np.full((simulations, 1), s0), paths])
    pct = {str(p): [float(x) for x in np.percentile(paths, p, axis=0)] for p in percentile_levels}
    terminal = paths[:, -1]
    term_pct = {str(p): float(np.percentile(terminal, p)) for p in percentile_levels}
    return MonteCarloResult(
        True,
        n,
        horizon_periods,
        simulations,
        seed,
        mu * periods_per_year,
        sigma * math.sqrt(periods_per_year),
        pct,
        term_pct,
        float((terminal < s0).mean()),
    )


# ---------------------------------------------------------------------------
# Series alignment helper
# ---------------------------------------------------------------------------


def align_on_dates(series: dict[str, list[tuple]]) -> tuple[list, dict[str, list]]:
    """`series[label] = [(date, value), ...]` -> common dates (sorted) and
    per-label values on exactly those dates. Only dates present in *every*
    series survive - no forward filling, no invented observations."""
    if not series:
        return [], {}
    common = None
    for points in series.values():
        dates = {d for d, _ in points}
        common = dates if common is None else common & dates
    common_sorted = sorted(common or [])
    aligned = {}
    for label, points in series.items():
        lookup = dict(points)
        aligned[label] = [lookup[d] for d in common_sorted]
    return common_sorted, aligned
