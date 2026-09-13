"""Chart tools beyond the moving-average family: Ichimoku, parabolic SAR,
pivot points, Fibonacci retracements, support/resistance levels and the
classic candlestick patterns — each with a one-paragraph reading so the
chart teaches while it shows. Pure numpy, no DB; missing OHLC yields `None`
for the tools that need it, never a reconstructed candle.
"""

# ruff: noqa: E501 — explanations are whole sentences.
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from app.domain.decision import support_resistance


def _nan_to_none(values) -> list[float | None]:
    return [None if v is None or (isinstance(v, float) and not math.isfinite(v)) else float(v) for v in values]


def _rolling(fn, arr: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        out[i] = fn(arr[i + 1 - window : i + 1])
    return out


# ---------------------------------------------------------------------------
# Ichimoku Kinko Hyo
# ---------------------------------------------------------------------------


@dataclass
class Ichimoku:
    tenkan: list[float | None]
    kijun: list[float | None]
    senkou_a: list[float | None]  # already shifted forward: index i = plotted on dates[i]
    senkou_b: list[float | None]
    chikou: list[float | None]  # close shifted back: index i = plotted on dates[i]
    future_dates: list[datetime]  # the 26 dates after the last bar where the cloud continues
    future_senkou_a: list[float | None]
    future_senkou_b: list[float | None]
    reading: str


def _future_weekdays(last: datetime, n: int) -> list[datetime]:
    out = []
    day = last
    while len(out) < n:
        day = day + timedelta(days=1)
        if day.weekday() < 5:
            out.append(day)
    return out


def ichimoku(dates: list[datetime], highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> Ichimoku | None:
    n = len(closes)
    if n < 52 + 26:
        return None
    mid = lambda h, lo, w: (_rolling(np.max, h, w) + _rolling(np.min, lo, w)) / 2  # noqa: E731
    tenkan = mid(highs, lows, 9)
    kijun = mid(highs, lows, 26)
    span_a_raw = (tenkan + kijun) / 2
    span_b_raw = mid(highs, lows, 52)
    shift = 26
    span_a = np.full(n, np.nan)
    span_b = np.full(n, np.nan)
    span_a[shift:] = span_a_raw[:-shift]
    span_b[shift:] = span_b_raw[:-shift]
    chikou = np.full(n, np.nan)
    chikou[:-shift] = closes[shift:]
    price = float(closes[-1])
    a, b = span_a[-1], span_b[-1]
    if np.isnan(a) or np.isnan(b):
        reading = "Nuage incomplet."
    elif price > max(a, b):
        reading = "Le cours est au-dessus du nuage : tendance haussière selon Ichimoku ; le nuage sert de support."
    elif price < min(a, b):
        reading = "Le cours est sous le nuage : tendance baissière selon Ichimoku ; le nuage sert de résistance."
    else:
        reading = "Le cours est dans le nuage : zone d'indécision, pas de tendance exploitable selon Ichimoku."
    if not np.isnan(tenkan[-1]) and not np.isnan(kijun[-1]):
        reading += (
            " Tenkan au-dessus de Kijun (élan positif)."
            if tenkan[-1] > kijun[-1]
            else " Tenkan sous Kijun (élan négatif)."
        )
    return Ichimoku(
        tenkan=_nan_to_none(tenkan),
        kijun=_nan_to_none(kijun),
        senkou_a=_nan_to_none(span_a),
        senkou_b=_nan_to_none(span_b),
        chikou=_nan_to_none(chikou),
        future_dates=_future_weekdays(dates[-1], shift),
        future_senkou_a=_nan_to_none(span_a_raw[-shift:]),
        future_senkou_b=_nan_to_none(span_b_raw[-shift:]),
        reading=reading,
    )


# ---------------------------------------------------------------------------
# Parabolic SAR
# ---------------------------------------------------------------------------


@dataclass
class ParabolicSar:
    values: list[float | None]
    trend: list[int]  # +1 rising (SAR below price), -1 falling
    reading: str


def parabolic_sar(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, step: float = 0.02, max_step: float = 0.2
) -> ParabolicSar | None:
    n = len(closes)
    if n < 5:
        return None
    sar = np.zeros(n)
    trend = np.zeros(n, dtype=int)
    up = closes[1] >= closes[0]
    ep = highs[0] if up else lows[0]
    af = step
    sar[0] = lows[0] if up else highs[0]
    trend[0] = 1 if up else -1
    for i in range(1, n):
        prev = sar[i - 1]
        cur = prev + af * (ep - prev)
        if up:
            cur = min(cur, lows[i - 1], lows[i - 2] if i >= 2 else lows[i - 1])
            if lows[i] < cur:  # reversal
                up = False
                cur = ep
                ep = lows[i]
                af = step
            else:
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + step, max_step)
        else:
            cur = max(cur, highs[i - 1], highs[i - 2] if i >= 2 else highs[i - 1])
            if highs[i] > cur:
                up = True
                cur = ep
                ep = highs[i]
                af = step
            else:
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + step, max_step)
        sar[i] = cur
        trend[i] = 1 if up else -1
    reading = (
        "Les points SAR sont sous le cours : tendance haussière ; le dernier point est le niveau de stop suiveur que la méthode propose."
        if trend[-1] == 1
        else "Les points SAR sont au-dessus du cours : tendance baissière ; un passage du cours au-dessus des points signalerait un retournement."
    )
    return ParabolicSar(values=_nan_to_none(sar), trend=[int(t) for t in trend], reading=reading)


# ---------------------------------------------------------------------------
# Pivot points (classic)
# ---------------------------------------------------------------------------


@dataclass
class PivotSet:
    period: str  # jour | semaine | mois
    based_on: str
    pivot: float
    r1: float
    r2: float
    r3: float
    s1: float
    s2: float
    s3: float


def _pivots(period: str, based_on: str, high: float, low: float, close: float) -> PivotSet:
    p = (high + low + close) / 3
    return PivotSet(
        period=period,
        based_on=based_on,
        pivot=p,
        r1=2 * p - low,
        r2=p + (high - low),
        r3=high + 2 * (p - low),
        s1=2 * p - high,
        s2=p - (high - low),
        s3=low - 2 * (high - p),
    )


def pivot_points(dates: list[datetime], highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> list[PivotSet]:
    out = []
    n = len(closes)
    if n >= 2:
        out.append(
            _pivots("jour", f"séance du {dates[-1]:%d/%m/%Y}", float(highs[-1]), float(lows[-1]), float(closes[-1]))
        )
    if n >= 6:
        w = slice(-6, -1)
        out.append(
            _pivots(
                "semaine", "5 dernières séances closes", float(highs[w].max()), float(lows[w].min()), float(closes[-2])
            )
        )
    if n >= 22:
        m = slice(-22, -1)
        out.append(
            _pivots(
                "mois", "21 dernières séances closes", float(highs[m].max()), float(lows[m].min()), float(closes[-2])
            )
        )
    return out


# ---------------------------------------------------------------------------
# Fibonacci retracements
# ---------------------------------------------------------------------------

FIB_RATIOS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)


@dataclass
class Fibonacci:
    swing_high: float
    swing_high_date: datetime
    swing_low: float
    swing_low_date: datetime
    direction: str  # hausse | baisse — the move being retraced
    levels: list[tuple[float, float]]  # (ratio, price)
    nearest_ratio: float | None
    reading: str


def fibonacci(dates: list[datetime], closes: np.ndarray) -> Fibonacci | None:
    n = len(closes)
    if n < 20:
        return None
    hi_i, lo_i = int(closes.argmax()), int(closes.argmin())
    hi, lo = float(closes[hi_i]), float(closes[lo_i])
    if hi == lo:
        return None
    direction = "hausse" if lo_i < hi_i else "baisse"
    # Retracing an up move: levels descend from the high; a down move: ascend from the low.
    levels = [(r, hi - r * (hi - lo)) if direction == "hausse" else (r, lo + r * (hi - lo)) for r in FIB_RATIOS]
    price = float(closes[-1])
    nearest = min(levels, key=lambda lv: abs(lv[1] - price))
    retraced = (hi - price) / (hi - lo) if direction == "hausse" else (price - lo) / (hi - lo)
    reading = (
        f"Sur la fenêtre, le mouvement de référence est une {direction} de {lo:.2f} à {hi:.2f}. Le cours actuel a "
        f"retracé {retraced * 100:.0f} % de ce mouvement, près du niveau {nearest[0] * 100:.1f} % ({nearest[1]:.2f}). "
        "Les niveaux 38,2 %, 50 % et 61,8 % sont ceux où les traders guettent un arrêt du repli ; au-delà de 78,6 %, "
        "le mouvement est considéré comme annulé. Repères conventionnels, sans fondement démontré — ils fonctionnent "
        "surtout parce que beaucoup les regardent."
    )
    return Fibonacci(hi, dates[hi_i], lo, dates[lo_i], direction, levels, nearest[0], reading)


# ---------------------------------------------------------------------------
# Candlestick patterns
# ---------------------------------------------------------------------------


@dataclass
class Pattern:
    index: int
    as_of: datetime
    name: str
    direction: str  # haussier | baissier | indecision
    explanation: str


PATTERN_TEXT = {
    "doji": "Ouverture et clôture presque égales : indécision, ni les acheteurs ni les vendeurs n'ont gagné la séance. Significatif surtout après une tendance marquée.",
    "marteau": "Petite bougie en haut, longue mèche basse après une baisse : les vendeurs ont poussé puis les acheteurs ont repris la main. Retournement haussier possible, à confirmer par la séance suivante.",
    "etoile_filante": "Petite bougie en bas, longue mèche haute après une hausse : les acheteurs ont poussé puis ont été rejetés. Retournement baissier possible.",
    "avalement_haussier": "Une bougie haussière englobe entièrement la bougie baissière précédente : les acheteurs reprennent le contrôle. Figure de retournement haussier classique.",
    "avalement_baissier": "Une bougie baissière englobe la bougie haussière précédente : les vendeurs reprennent le contrôle. Figure de retournement baissier classique.",
    "etoile_du_matin": "Trois bougies : forte baisse, petite bougie d'hésitation, forte hausse. Retournement haussier après une baisse.",
    "etoile_du_soir": "Trois bougies : forte hausse, petite bougie d'hésitation, forte baisse. Retournement baissier après une hausse.",
}


def candlestick_patterns(dates: list[datetime], opens, highs, lows, closes, *, last_n: int = 60) -> list[Pattern]:
    o, h, lo, c = (np.asarray(x, dtype=float) for x in (opens, highs, lows, closes))
    n = len(c)
    out: list[Pattern] = []
    start = max(2, n - last_n)
    for i in range(start, n):
        body = abs(c[i] - o[i])
        rng = h[i] - lo[i]
        if rng <= 0:
            continue
        upper = h[i] - max(o[i], c[i])
        lower = min(o[i], c[i]) - lo[i]
        prev_trend_down = c[i - 1] < c[max(0, i - 6)]
        prev_trend_up = c[i - 1] > c[max(0, i - 6)]
        if body <= 0.1 * rng:
            out.append(Pattern(i, dates[i], "doji", "indecision", PATTERN_TEXT["doji"]))
            continue
        if lower >= 2 * body and upper <= 0.3 * body and prev_trend_down:
            out.append(Pattern(i, dates[i], "marteau", "haussier", PATTERN_TEXT["marteau"]))
        elif upper >= 2 * body and lower <= 0.3 * body and prev_trend_up:
            out.append(Pattern(i, dates[i], "etoile_filante", "baissier", PATTERN_TEXT["etoile_filante"]))
        prev_body = abs(c[i - 1] - o[i - 1])
        if c[i] > o[i] and c[i - 1] < o[i - 1] and o[i] <= c[i - 1] and c[i] >= o[i - 1] and body > prev_body:
            out.append(Pattern(i, dates[i], "avalement_haussier", "haussier", PATTERN_TEXT["avalement_haussier"]))
        elif c[i] < o[i] and c[i - 1] > o[i - 1] and o[i] >= c[i - 1] and c[i] <= o[i - 1] and body > prev_body:
            out.append(Pattern(i, dates[i], "avalement_baissier", "baissier", PATTERN_TEXT["avalement_baissier"]))
        b2, b1 = abs(c[i - 2] - o[i - 2]), abs(c[i - 1] - o[i - 1])
        if b2 > 0 and b1 <= 0.3 * b2:
            if c[i - 2] < o[i - 2] and c[i] > o[i] and c[i] > (o[i - 2] + c[i - 2]) / 2:
                out.append(Pattern(i, dates[i], "etoile_du_matin", "haussier", PATTERN_TEXT["etoile_du_matin"]))
            elif c[i - 2] > o[i - 2] and c[i] < o[i] and c[i] < (o[i - 2] + c[i - 2]) / 2:
                out.append(Pattern(i, dates[i], "etoile_du_soir", "baissier", PATTERN_TEXT["etoile_du_soir"]))
    return out


# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------


@dataclass
class ChartTools:
    has_ohlc: bool
    ichimoku: Ichimoku | None
    sar: ParabolicSar | None
    pivots: list[PivotSet]
    fibonacci: Fibonacci | None
    supports: list[float]
    resistances: list[float]
    patterns: list[Pattern] = field(default_factory=list)


def chart_tools(dates: list[datetime], opens, highs, lows, closes) -> ChartTools:
    c = np.asarray(closes, dtype=float)
    has_ohlc = opens is not None and highs is not None and lows is not None and len(highs) == len(c) and len(c) > 0
    supports, resistances = support_resistance(c[-252:])
    if not has_ohlc:
        return ChartTools(False, None, None, [], fibonacci(dates, c), supports, resistances, [])
    h, lo = np.asarray(highs, dtype=float), np.asarray(lows, dtype=float)
    return ChartTools(
        has_ohlc=True,
        ichimoku=ichimoku(dates, h, lo, c),
        sar=parabolic_sar(h, lo, c),
        pivots=pivot_points(dates, h, lo, c),
        fibonacci=fibonacci(dates, c),
        supports=supports,
        resistances=resistances,
        patterns=candlestick_patterns(dates, opens, h, lo, c),
    )
