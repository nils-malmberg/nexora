"""Decision aid: recognised, documented readings of an instrument and of a
portfolio, written for someone who has never opened a finance textbook.

Each `Signal` is one method (trend, momentum, valuation ratio, analyst
consensus, risk measure…) applied to the data the app already holds, with:

- a *reading*: `favorable` (the method's textbook reading leans towards
  buying / holding), `defavorable` (leans towards selling / not buying),
  `neutre` (nothing to say), `indisponible` (no data — never guessed);
- an *evidence* grade: how well the academic literature supports the
  method as a predictor (`forte` / `moyenne` / `faible`);
- a plain-French explanation of what was measured and why it reads so.

The readings are generic: they depend only on the instrument, never on the
user's situation, goals or holdings, and they are counted, not weighted, so
the summary is a tally of methods and not a verdict. That is the boundary
specs/PRODUCT_SPEC.md draws: information, not personalised advice, no
execution. Everything is pure (no DB) so it is unit-testable.
"""

# ruff: noqa: E501 — prose-heavy module: the explanations are sentences, kept whole for editing.
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np

from app.domain import quant

READINGS = ("favorable", "defavorable", "neutre", "indisponible")
HORIZONS = ("court_terme", "long_terme", "transversal")

DISCLAIMER = (
    "Ces lectures appliquent mécaniquement des méthodes reconnues aux données disponibles. Aucune n'est "
    "infaillible, plusieurs se contredisent souvent, et leur pouvoir prédictif documenté est faible à moyen. "
    "Elles décrivent l'instrument, pas votre situation : le jugement, l'horizon et la décision restent les vôtres. "
    "Ceci n'est ni un conseil en investissement ni un signal d'ordre."
)


@dataclass
class Signal:
    key: str
    family: str  # tendance | momentum | volatilite | valorisation | qualite | consensus | risque | prediction
    horizon: str
    label: str
    reading: str
    detail: str
    value: str | None = None
    strength: str = "moyen"  # faible | moyen | fort
    evidence: str = "moyenne"  # forte | moyenne | faible — academic support for the method
    help_slug: str | None = None


@dataclass
class Tally:
    favorable: int = 0
    defavorable: int = 0
    neutre: int = 0
    indisponible: int = 0

    def add(self, reading: str) -> None:
        setattr(self, reading, getattr(self, reading) + 1)

    @property
    def available(self) -> int:
        return self.favorable + self.defavorable + self.neutre


def tally(signals: list[Signal]) -> Tally:
    t = Tally()
    for s in signals:
        t.add(s.reading)
    return t


def _fmt(value: float | None, digits: int = 2, suffix: str = "") -> str | None:
    if value is None or not math.isfinite(value):
        return None
    return f"{value:.{digits}f}{suffix}"


def _pct(value: float | None, digits: int = 1) -> str | None:
    return _fmt(value * 100, digits, " %") if value is not None and math.isfinite(value) else None


def _ema_f(values: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) < window:
        return out
    alpha = 2.0 / (window + 1)
    out[window - 1] = values[:window].mean()
    for i in range(window, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def _s(n: int) -> str:
    return "s" if n > 1 else ""


def _last(arr: np.ndarray) -> float | None:
    if len(arr) == 0:
        return None
    v = float(arr[-1])
    return v if math.isfinite(v) else None


# ---------------------------------------------------------------------------
# Technical / statistical readings of one price series
# ---------------------------------------------------------------------------


def technical_signals(closes, *, periods_per_year: int = quant.TRADING_DAYS) -> list[Signal]:
    c = quant._f(closes)
    n = len(c)
    signals: list[Signal] = []
    price = _last(c)

    def unavailable(key, family, horizon, label, needed):
        signals.append(
            Signal(
                key,
                family,
                horizon,
                label,
                "indisponible",
                f"Il faut au moins {needed} clôtures ({n} disponibles).",
                None,
            )
        )

    # --- trend: price vs SMA50 / SMA200 ------------------------------------
    if n >= 200 and price is not None:
        sma50 = _last(quant._sma_f(c, 50))
        sma200 = _last(quant._sma_f(c, 200))
        above50 = price > sma50
        above200 = price > sma200
        if above50 and above200:
            reading, strength, why = "favorable", "fort", "au-dessus de ses deux moyennes : tendance haussière établie"
        elif not above50 and not above200:
            reading, strength, why = (
                "defavorable",
                "fort",
                "en dessous de ses deux moyennes : tendance baissière établie",
            )
        else:
            reading, strength, why = "neutre", "faible", "entre ses deux moyennes : tendance indécise"
        signals.append(
            Signal(
                "tendance_sma",
                "tendance",
                "court_terme",
                "Tendance (cours vs moyennes 50 et 200 jours)",
                reading,
                f"Le cours ({_fmt(price)}) est {why}. La moyenne mobile lisse le bruit quotidien : un cours "
                "durablement "
                "au-dessus signale que les acheteurs dominent, en dessous que les vendeurs dominent.",
                f"SMA50 {_fmt(sma50)} · SMA200 {_fmt(sma200)}",
                strength,
                "moyenne",
                "indicateurs-techniques",
            )
        )
        cross = "favorable" if sma50 > sma200 else "defavorable"
        signals.append(
            Signal(
                "croisement_sma",
                "tendance",
                "court_terme",
                "Croisement des moyennes (« golden / death cross »)",
                cross,
                "La moyenne 50 jours est "
                + ("au-dessus" if cross == "favorable" else "en dessous")
                + " de la moyenne 200 jours. Le passage au-dessus (« golden cross ») est lu comme le début d'une "
                "tendance haussière, le passage en dessous (« death cross ») comme le début d'une tendance baissière. "
                "Signal lent : il confirme une tendance déjà en cours plus qu'il ne l'anticipe.",
                f"SMA50 − SMA200 = {_fmt(sma50 - sma200)}",
                "moyen",
                "moyenne",
                "indicateurs-techniques",
            )
        )
    else:
        unavailable("tendance_sma", "tendance", "court_terme", "Tendance (cours vs moyennes 50 et 200 jours)", 200)
        unavailable("croisement_sma", "tendance", "court_terme", "Croisement des moyennes", 200)

    # --- momentum 12-1 (Jegadeesh & Titman) -------------------------------
    if n >= 252 + 21:
        mom = c[-22] / c[-253] - 1.0 if c[-253] > 0 else None
        if mom is not None:
            reading = "favorable" if mom > 0.05 else "defavorable" if mom < -0.05 else "neutre"
            signals.append(
                Signal(
                    "momentum_12_1",
                    "momentum",
                    "court_terme",
                    "Momentum 12 mois (hors dernier mois)",
                    reading,
                    f"Sur les 12 derniers mois en ignorant le dernier, le cours a varié de {_pct(mom)}. Les titres qui "
                    "ont le plus monté sur un an tendent, en moyenne, à continuer quelques mois (effet momentum, l'une "
                    "des anomalies les mieux documentées) — avec des retournements brutaux dans les crises.",
                    _pct(mom),
                    "fort" if abs(mom) > 0.2 else "moyen",
                    "forte",
                    "efficience-des-marches",
                )
            )
    else:
        unavailable("momentum_12_1", "momentum", "court_terme", "Momentum 12 mois (hors dernier mois)", 273)

    # --- RSI 14 ------------------------------------------------------------
    if n >= 30:
        rsi = _last(quant._rsi_f(c, 14))
        if rsi is not None:
            if rsi < 30:
                reading, why = (
                    "favorable",
                    "en zone de « survente » : les baisses récentes ont été très fortes, un rebond est souvent lu "
                    "comme plus probable",
                )
            elif rsi > 70:
                reading, why = (
                    "defavorable",
                    "en zone de « surachat » : les hausses récentes ont été très fortes, une pause ou un repli est "
                    "souvent lu comme plus probable",
                )
            else:
                reading, why = "neutre", "en zone intermédiaire : ni surachat ni survente"
            signals.append(
                Signal(
                    "rsi",
                    "momentum",
                    "court_terme",
                    "RSI 14 jours (surachat / survente)",
                    reading,
                    f"Le RSI vaut {_fmt(rsi, 0)}, {why}. Le RSI (0–100) compare la taille des hausses et des baisses "
                    "des 14 derniers jours. Lecture à contre-courant : elle fonctionne mieux dans un marché sans "
                    "tendance et peut rester longtemps « extrême » dans une tendance forte.",
                    _fmt(rsi, 0),
                    "fort" if rsi < 20 or rsi > 80 else "moyen",
                    "faible",
                    "indicateurs-techniques",
                )
            )
    else:
        unavailable("rsi", "momentum", "court_terme", "RSI 14 jours", 30)

    # --- MACD --------------------------------------------------------------
    if n >= 60:
        macd = _ema_f(c, 12) - _ema_f(c, 26)
        valid = macd[~np.isnan(macd)]
        sig_line = _ema_f(valid, 9) if len(valid) >= 9 else np.array([])
        m, sg = _last(valid), _last(sig_line)
        if m is not None and sg is not None:
            reading = "favorable" if m > sg else "defavorable"
            signals.append(
                Signal(
                    "macd",
                    "momentum",
                    "court_terme",
                    "MACD (élan récent)",
                    reading,
                    "La ligne MACD (écart entre moyennes 12 et 26 jours) est "
                    + ("au-dessus" if reading == "favorable" else "en dessous")
                    + " de sa ligne de signal : l'élan des dernières semaines est "
                    + ("haussier" if reading == "favorable" else "baissier")
                    + ". Indicateur très suivi mais réactif : il donne de faux signaux dans un marché qui hésite.",
                    f"MACD {_fmt(m, 3)} · signal {_fmt(sg, 3)}",
                    "moyen",
                    "faible",
                    "indicateurs-techniques",
                )
            )
    else:
        unavailable("macd", "momentum", "court_terme", "MACD", 60)

    # --- Bollinger %B --------------------------------------------------------
    if n >= 20 and price is not None:
        means, stds = quant.rolling_mean_std(c, 20)
        mid, sd = means[-1], stds[-1]
        if mid is not None and sd:
            pct_b = (price - (mid - 2 * sd)) / (4 * sd)
            reading = "favorable" if pct_b < 0 else "defavorable" if pct_b > 1 else "neutre"
            signals.append(
                Signal(
                    "bollinger",
                    "volatilite",
                    "court_terme",
                    "Bandes de Bollinger (position du cours)",
                    reading,
                    f"Le cours se situe à {_fmt(pct_b * 100, 0)} % de la largeur des bandes (0 % = bande basse, 100 "
                    "% = "
                    "bande haute). Sous la bande basse, le titre est « anormalement » bas par rapport à ses 20 "
                    "derniers "
                    "jours, au-dessus de la bande haute « anormalement » haut — un écart qui a tendance à se résorber, "
                    "sauf quand une vraie tendance démarre.",
                    f"%B {_fmt(pct_b, 2)}",
                    "moyen",
                    "faible",
                    "indicateurs-techniques",
                )
            )
    else:
        unavailable("bollinger", "volatilite", "court_terme", "Bandes de Bollinger", 20)

    # --- distance to 52-week high / low (informational) -----------------------
    if n >= 200 and price is not None:
        window = c[-252:] if n >= 252 else c
        hi, lo = float(window.max()), float(window.min())
        from_high = price / hi - 1.0 if hi > 0 else None
        from_low = price / lo - 1.0 if lo > 0 else None
        if from_high is not None and from_low is not None:
            if from_high > -0.05:
                reading, why = (
                    "favorable",
                    "proche de son plus haut sur un an — les titres au plus haut ont tendance à poursuivre (effet « "
                    "52-week high »)",
                )
            elif from_high < -0.4:
                reading, why = (
                    "neutre",
                    "très loin de son plus haut sur un an : fortement replié — cela peut être une occasion ou une "
                    "dégradation durable, l'indicateur ne tranche pas",
                )
            else:
                reading, why = "neutre", "à distance intermédiaire de ses extrêmes annuels"
            signals.append(
                Signal(
                    "plus_haut_52s",
                    "tendance",
                    "court_terme",
                    "Position dans la fourchette sur un an",
                    reading,
                    f"Le cours est à {_pct(from_high)} de son plus haut et à {_pct(from_low, 1)} de son plus bas sur "
                    f"un an : {why}.",
                    f"plus haut {_fmt(hi)} · plus bas {_fmt(lo)}",
                    "faible",
                    "moyenne",
                    "efficience-des-marches",
                )
            )

    # --- risk: volatility, drawdown, Sharpe over the last year ----------------
    year = c[-252:] if n >= 252 else c
    stats = quant.return_stats(year, periods_per_year=periods_per_year)
    if stats.has_sufficient_data and stats.volatility_annualized is not None:
        vol = stats.volatility_annualized
        level = "faible" if vol < 0.2 else "moyenne" if vol < 0.4 else "élevée"
        signals.append(
            Signal(
                "volatilite",
                "risque",
                "transversal",
                "Volatilité annualisée (amplitude des variations)",
                "neutre",
                f"Volatilité {level} : {_pct(vol)} par an. C'est l'ordre de grandeur des variations à attendre sur "
                "un an "
                "(à titre de repère : un grand indice d'actions ~15–20 %, une action individuelle ~25–40 %, une crypto "
                "> 60 %). Ce n'est ni bon ni mauvais : c'est le prix du risque que vous prenez.",
                _pct(vol),
                "moyen",
                "forte",
                "volatilite-drawdown",
            )
        )
        mdd = stats.max_drawdown
        if mdd is not None:
            signals.append(
                Signal(
                    "drawdown_1a",
                    "risque",
                    "transversal",
                    "Pire repli sur un an",
                    "neutre",
                    f"Sur les douze derniers mois, le titre a perdu jusqu'à {_pct(mdd)} depuis un sommet avant de "
                    "remonter (ou pas encore). C'est la perte qu'il fallait pouvoir supporter pour rester investi.",
                    _pct(mdd),
                    "moyen",
                    "forte",
                    "volatilite-drawdown",
                )
            )
        if stats.sharpe is not None:
            reading = "favorable" if stats.sharpe > 1 else "defavorable" if stats.sharpe < 0 else "neutre"
            signals.append(
                Signal(
                    "sharpe_1a",
                    "risque",
                    "transversal",
                    "Ratio de Sharpe sur un an (rendement par unité de risque)",
                    reading,
                    f"Sharpe {_fmt(stats.sharpe)} : rendement annualisé {_pct(stats.mean_return_annualized)} pour une "
                    f"volatilité de {_pct(vol)}. Au-dessus de 1, le risque pris a été bien rémunéré ; négatif, il a "
                    "été pris pour perdre. Mesure du passé : un bon Sharpe ne se prolonge pas mécaniquement.",
                    _fmt(stats.sharpe),
                    "moyen",
                    "moyenne",
                    "sharpe-sortino-calmar",
                )
            )
    else:
        unavailable("volatilite", "risque", "transversal", "Volatilité annualisée", 21)

    return signals


# ---------------------------------------------------------------------------
# Fundamental readings (valuation, quality, consensus)
# ---------------------------------------------------------------------------


def _dec(data: dict, key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    try:
        f = float(Decimal(str(value)))
    except (ArithmeticError, ValueError):
        return None
    return f if math.isfinite(f) else None


def fundamental_signals(data: dict | None) -> list[Signal]:
    """`data` is the stored `Fundamentals.as_dict()` (fractions, not
    percents). Thresholds are the classic Graham-style rules of thumb —
    stated in every explanation, since they vary by sector."""
    signals: list[Signal] = []
    d = data or {}

    def na(key, family, label, why="Donnée non fournie par la source."):
        signals.append(Signal(key, family, "long_terme", label, "indisponible", why))

    pe = _dec(d, "pe")
    if pe is None:
        na("per", "valorisation", "PER (prix / bénéfice par action)")
    else:
        if pe <= 0:
            reading, why = (
                "defavorable",
                "l'entreprise perd de l'argent (bénéfice négatif) : le PER n'a pas de sens et c'est en soi un signal "
                "de prudence",
            )
        elif pe < 15:
            reading, why = (
                "favorable",
                "bon marché par rapport aux repères classiques (< 15) — à condition que les bénéfices ne soient pas "
                "en train de s'effondrer",
            )
        elif pe <= 25:
            reading, why = "neutre", "dans la fourchette habituelle (15–25)"
        else:
            reading, why = (
                "defavorable",
                "cher (> 25) : le marché paie une forte croissance future, qui doit se réaliser pour justifier le prix",
            )
        signals.append(
            Signal(
                "per",
                "valorisation",
                "long_terme",
                "PER (prix / bénéfice par action)",
                reading,
                f"PER de {_fmt(pe, 1)} : {why}. Le PER dit combien d'années de bénéfice actuel on paie pour une "
                "action. "
                "Il se compare surtout au secteur et à l'historique du titre ; un PER bas peut aussi signaler une "
                "entreprise en difficulté (« value trap »).",
                _fmt(pe, 1),
                "moyen",
                "forte",
                "analyse-fondamentale",
            )
        )

    pb = _dec(d, "pb")
    if pb is None:
        na("pb", "valorisation", "Prix / actif net comptable")
    else:
        reading = "favorable" if 0 < pb < 1.5 else "defavorable" if pb > 5 else "neutre"
        signals.append(
            Signal(
                "pb",
                "valorisation",
                "long_terme",
                "Prix / actif net comptable (P/B)",
                reading,
                f"P/B de {_fmt(pb, 2)} : "
                + (
                    "l'action se paie moins de 1,5 fois la valeur comptable de l'entreprise — historiquement, les "
                    "titres « value » de ce type ont mieux rendu en moyenne"
                    if reading == "favorable"
                    else "plus de 5 fois la valeur comptable : le prix repose sur des actifs immatériels ou une croissance attendue, pas sur le bilan"
                    if reading == "defavorable"
                    else "valorisation comptable dans la moyenne"
                )
                + ". Peu pertinent pour les sociétés de logiciels ou de services, dont l'essentiel de la valeur n'est pas au bilan.",
                _fmt(pb, 2),
                "faible",
                "forte",
                "analyse-fondamentale",
            )
        )

    dy = _dec(d, "dividend_yield")
    if dy is None:
        na("rendement_dividende", "valorisation", "Rendement du dividende")
    else:
        reading = "favorable" if dy >= 0.03 else "neutre"
        signals.append(
            Signal(
                "rendement_dividende",
                "valorisation",
                "long_terme",
                "Rendement du dividende",
                reading,
                f"Dividende de {_pct(dy)} par an au cours actuel"
                + (
                    " : un revenu régulier notable, si l'entreprise peut le maintenir (vérifier que le bénéfice le "
                    "couvre)"
                    if reading == "favorable"
                    else " : faible ou nul — l'entreprise réinvestit ses bénéfices ou n'en a pas, ce qui n'est pas un défaut en soi"
                )
                + ". Un rendement très élevé (> 8 %) est souvent le signe d'un cours qui a chuté, pas d'une générosité.",
                _pct(dy),
                "faible",
                "moyenne",
                "revenus-du-portefeuille",
            )
        )

    g = _dec(d, "eps_growth")
    if g is None:
        na("croissance_bpa", "qualite", "Croissance du bénéfice par action")
    else:
        reading = "favorable" if g > 0.10 else "defavorable" if g < 0 else "neutre"
        signals.append(
            Signal(
                "croissance_bpa",
                "qualite",
                "long_terme",
                "Croissance du bénéfice par action",
                reading,
                f"Bénéfice par action en variation de {_pct(g)} sur un an : "
                + (
                    "croissance soutenue"
                    if reading == "favorable"
                    else "bénéfice en recul"
                    if reading == "defavorable"
                    else "croissance modeste"
                )
                + ". Sur le long terme, le cours suit les bénéfices ; une année seule reste toutefois bruitée (effets exceptionnels).",
                _pct(g),
                "moyen",
                "moyenne",
                "analyse-fondamentale",
            )
        )

    roe = _dec(d, "roe")
    if roe is None:
        na("roe", "qualite", "Rentabilité des capitaux propres (ROE)")
    else:
        reading = "favorable" if roe > 0.15 else "defavorable" if roe < 0.05 else "neutre"
        signals.append(
            Signal(
                "roe",
                "qualite",
                "long_terme",
                "Rentabilité des capitaux propres (ROE)",
                reading,
                f"ROE de {_pct(roe)} : l'entreprise dégage ce bénéfice pour 100 de capitaux apportés par ses "
                "actionnaires "
                + (
                    "— un niveau élevé, signe d'un avantage concurrentiel ou d'un fort endettement (voir la dette)"
                    if reading == "favorable"
                    else "— un niveau faible : le capital est mal rémunéré"
                    if reading == "defavorable"
                    else "— un niveau ordinaire"
                )
                + ".",
                _pct(roe),
                "moyen",
                "moyenne",
                "analyse-fondamentale",
            )
        )

    margin = _dec(d, "net_margin")
    if margin is not None:
        reading = "favorable" if margin > 0.10 else "defavorable" if margin < 0 else "neutre"
        signals.append(
            Signal(
                "marge_nette",
                "qualite",
                "long_terme",
                "Marge nette",
                reading,
                f"Sur 100 de chiffre d'affaires, il reste {_fmt(margin * 100, 1)} de bénéfice net"
                + (
                    " : activité très rentable"
                    if reading == "favorable"
                    else " : l'entreprise est en perte"
                    if reading == "defavorable"
                    else ""
                )
                + ". Se compare surtout au sein d'un même secteur (la distribution vit avec 2 %, le logiciel avec 25 %).",
                _pct(margin),
                "faible",
                "moyenne",
                "analyse-fondamentale",
            )
        )

    de = _dec(d, "debt_to_equity")
    if de is None:
        na("dette", "qualite", "Endettement (dette / capitaux propres)")
    else:
        reading = "favorable" if 0 <= de < 0.5 else "defavorable" if de > 2 else "neutre"
        signals.append(
            Signal(
                "dette",
                "qualite",
                "long_terme",
                "Endettement (dette / capitaux propres)",
                reading,
                f"Dette égale à {_fmt(de, 2)} fois les capitaux propres : "
                + (
                    "bilan peu endetté, plus de marge en cas de coup dur"
                    if reading == "favorable"
                    else "fort endettement — les intérêts pèsent et une hausse des taux ou une baisse d'activité fait mal"
                    if reading == "defavorable"
                    else "endettement modéré"
                )
                + ". Les banques et les services publics fonctionnent structurellement avec plus de dette : comparer au secteur.",
                _fmt(de, 2),
                "moyen",
                "moyenne",
                "analyse-fondamentale",
            )
        )

    buy, hold, sell = d.get("analyst_buy"), d.get("analyst_hold"), d.get("analyst_sell")
    if buy is None or hold is None or sell is None or (buy + hold + sell) == 0:
        na(
            "consensus_analystes",
            "consensus",
            "Consensus des analystes",
            "Aucun consensus d'analystes publié par la source.",
        )
    else:
        total = buy + hold + sell
        buy_share, sell_share = buy / total, sell / total
        reading = "favorable" if buy_share >= 0.6 else "defavorable" if sell_share >= 0.3 else "neutre"
        signals.append(
            Signal(
                "consensus_analystes",
                "consensus",
                "long_terme",
                "Consensus des analystes",
                reading,
                f"{buy} avis à l'achat, {hold} à conserver, {sell} à la vente ({_pct(buy_share, 0)} d'avis positifs"
                + (f", période {d.get('analyst_period')}" if d.get("analyst_period") else "")
                + "). Les analystes sont structurellement optimistes (peu de « vendre ») et leurs avis suivent souvent "
                "le cours plus qu'ils ne l'anticipent ; un consensus très négatif est plus informatif qu'un "
                "consensus positif.",
                f"{buy} / {hold} / {sell}",
                "faible",
                "faible",
                "consensus-analystes",
            )
        )

    beta = _dec(d, "beta")
    if beta is not None:
        level = "défensif" if beta < 0.8 else "proche du marché" if beta <= 1.2 else "amplificateur"
        signals.append(
            Signal(
                "beta",
                "risque",
                "transversal",
                "Bêta (sensibilité au marché)",
                "neutre",
                f"Bêta de {_fmt(beta, 2)} : titre {level}. Quand le marché varie de 1 %, ce titre varie en moyenne de "
                f"{_fmt(beta, 2)} %. Ni bon ni mauvais : un bêta élevé amplifie les hausses comme les baisses.",
                _fmt(beta, 2),
                "faible",
                "forte",
                "capm-beta",
            )
        )
    return signals


# ---------------------------------------------------------------------------
# Prediction module (experimental) as one more, clearly labelled reading
# ---------------------------------------------------------------------------


def prediction_signal(forecast: dict | None, metrics: dict | None, horizon_days: int | None) -> Signal | None:
    if not forecast:
        return None
    expected = forecast.get("expected_log_return", forecast.get("expected_return"))
    if expected is None:
        return None
    try:
        exp = math.exp(float(expected)) - 1.0  # log-return → simple return
    except (TypeError, ValueError, OverflowError):
        return None
    meta = (metrics or {}).get("meta") or {}
    direction = meta.get("direction_accuracy")
    naive = ((metrics or {}).get("naive") or {}).get("mae")
    meta_mae = meta.get("mae")
    beats = naive is not None and meta_mae is not None and meta_mae < naive
    trusted = direction is not None and direction > 0.55 and beats
    if not trusted:
        reading = "neutre"
        why = "mais, en validation hors échantillon, le métamodèle ne fait pas mieux que le benchmark naïf : lecture à ignorer"
    else:
        reading = "favorable" if exp > 0 else "defavorable" if exp < 0 else "neutre"
        why = f"avec une précision de direction hors échantillon de {_pct(direction, 0)} — meilleure que le hasard, pas fiable pour autant"
    return Signal(
        "prediction",
        "prediction",
        "court_terme",
        f"Métamodèle de prédiction (horizon {horizon_days or '?'} j, expérimental)",
        reading,
        f"Dernière prévision : {_pct(exp)} de rendement attendu {why}. Module expérimental : il illustre ce qu'un "
        "modèle apprend du passé, il ne prédit pas l'avenir.",
        _pct(exp),
        "faible",
        "faible",
        "prediction-walk-forward",
    )


# ---------------------------------------------------------------------------
# Instrument summary
# ---------------------------------------------------------------------------


@dataclass
class HorizonSummary:
    horizon: str
    label: str
    tally: Tally
    text: str


@dataclass
class InstrumentAid:
    signals: list[Signal]
    tally: Tally
    horizons: list[HorizonSummary]
    overall: str
    disclaimer: str = DISCLAIMER


HORIZON_LABELS = {
    "court_terme": "Court terme (semaines à mois) — analyse technique",
    "long_terme": "Long terme (années) — fondamentaux",
    "transversal": "Risque — quel que soit l'horizon",
}


def _horizon_text(t: Tally) -> str:
    if t.available == 0:
        return "Aucune lecture disponible."
    parts = []
    if t.favorable:
        parts.append(f"{t.favorable} favorable{'s' if t.favorable > 1 else ''}")
    if t.defavorable:
        parts.append(f"{t.defavorable} défavorable{'s' if t.defavorable > 1 else ''}")
    if t.neutre:
        parts.append(f"{t.neutre} neutre{'s' if t.neutre > 1 else ''}")
    text = ", ".join(parts) + f" sur {t.available} lecture{'s' if t.available > 1 else ''}"
    if t.favorable > t.defavorable and t.favorable >= 2:
        text += " : les méthodes penchent plutôt du côté favorable"
    elif t.defavorable > t.favorable and t.defavorable >= 2:
        text += " : les méthodes penchent plutôt du côté défavorable"
    elif t.favorable == t.defavorable and t.favorable > 0:
        text += " : les méthodes se contredisent"
    else:
        text += " : pas de tendance nette"
    if t.indisponible:
        text += f" ({t.indisponible} indisponible{'s' if t.indisponible > 1 else ''})"
    return text + "."


def summarize_instrument(signals: list[Signal]) -> InstrumentAid:
    horizons = []
    for horizon in HORIZONS:
        t = tally([s for s in signals if s.horizon == horizon])
        horizons.append(HorizonSummary(horizon, HORIZON_LABELS[horizon], t, _horizon_text(t)))
    total = tally(signals)
    court = next(h.tally for h in horizons if h.horizon == "court_terme")
    long_ = next(h.tally for h in horizons if h.horizon == "long_terme")
    if total.available == 0:
        overall = "Pas assez de données pour appliquer une méthode : il faut un historique de cours (et, pour les fondamentaux, une source configurée)."
    else:
        overall = (
            f"{total.favorable} lecture{_s(total.favorable)} favorable{_s(total.favorable)}, "
            f"{total.defavorable} défavorable{_s(total.defavorable)}, {total.neutre} neutre{_s(total.neutre)} "
            f"sur {total.available} disponibles. "
        )
        if long_.available == 0:
            overall += "Les fondamentaux sont indisponibles : seul le court terme est couvert. "
        if court.favorable > court.defavorable and long_.defavorable > long_.favorable:
            overall += "Court terme favorable mais fondamentaux défavorables : typique d'un titre porté par l'élan plus que par ses résultats."
        elif court.defavorable > court.favorable and long_.favorable > long_.defavorable:
            overall += "Fondamentaux favorables mais court terme défavorable : le marché boude un titre que les ratios jugent sain — patience ou raison cachée ?"
        elif total.favorable > total.defavorable:
            overall += "Une majorité de méthodes penche du côté favorable — à confronter à votre horizon et à ce que vous détenez déjà."
        elif total.defavorable > total.favorable:
            overall += "Une majorité de méthodes penche du côté défavorable — ce qui vaut pour un achat comme pour une position déjà ouverte."
        else:
            overall += "Les méthodes ne dégagent pas de direction : c'est fréquent, et c'est une information en soi."
    return InstrumentAid(signals=signals, tally=total, horizons=horizons, overall=overall)


# ---------------------------------------------------------------------------
# Portfolio check-up
# ---------------------------------------------------------------------------


@dataclass
class PositionInput:
    symbol: str
    asset_class: str
    currency: str
    value_base: float | None
    unrealized_pnl_pct: float | None = None


@dataclass
class CheckupInput:
    base_currency: str
    positions: list[PositionInput]
    cash_base: float
    total_base: float
    target_allocation: dict[str, float] | None = None
    avg_correlation: float | None = None
    correlation_pairs: int = 0
    volatility_annualized: float | None = None
    max_drawdown: float | None = None
    missing_prices: int = 0


@dataclass
class PortfolioCheckup:
    signals: list[Signal]
    tally: Tally
    overall: str
    allocation: dict[str, float] = field(default_factory=dict)
    drift: dict[str, float] = field(default_factory=dict)
    disclaimer: str = DISCLAIMER


def portfolio_checkup(inp: CheckupInput) -> PortfolioCheckup:
    signals: list[Signal] = []
    total = inp.total_base
    valued = [p for p in inp.positions if p.value_base is not None]
    allocation: dict[str, float] = {}
    if total > 0:
        for p in valued:
            allocation[p.asset_class] = allocation.get(p.asset_class, 0.0) + p.value_base / total
        if inp.cash_base:
            allocation["tresorerie"] = inp.cash_base / total

    # --- concentration per instrument --------------------------------------
    if total > 0 and valued:
        biggest = max(valued, key=lambda p: p.value_base)
        share = biggest.value_base / total
        reading = "defavorable" if share > 0.25 else "favorable" if share < 0.15 else "neutre"
        signals.append(
            Signal(
                "concentration_instrument",
                "diversification",
                "transversal",
                "Plus grosse ligne",
                reading,
                f"{biggest.symbol} pèse {_pct(share, 0)} du portefeuille"
                + (
                    " : au-delà de 25 %, un accident sur ce seul titre marque durablement l'ensemble — la règle de "
                    "bon sens est de ne pas dépendre d'une ligne"
                    if reading == "defavorable"
                    else " : aucune ligne ne domine"
                    if reading == "favorable"
                    else " : concentration notable mais courante"
                )
                + ".",
                _pct(share, 0),
                "fort" if share > 0.4 else "moyen",
                "forte",
                "correlation-diversification",
            )
        )
    nb = len(valued)
    reading = "defavorable" if nb < 5 else "favorable" if nb >= 10 else "neutre"
    signals.append(
        Signal(
            "nombre_lignes",
            "diversification",
            "transversal",
            "Nombre de lignes",
            reading,
            f"{nb} position{'s' if nb > 1 else ''} valorisée{'s' if nb > 1 else ''}"
            + (
                " : en dessous de 5 titres, le risque propre à chaque entreprise n'est pas dilué (un ETF large règle "
                "le problème en une ligne)"
                if reading == "defavorable"
                else " : le risque spécifique à chaque titre est largement dilué"
                if reading == "favorable"
                else " : diversification partielle"
            )
            + ".",
            str(nb),
            "moyen",
            "forte",
            "correlation-diversification",
        )
    )

    # --- asset-class and currency concentration --------------------------------
    if allocation:
        cls, share = max(
            ((k, v) for k, v in allocation.items() if k != "tresorerie"), key=lambda kv: kv[1], default=(None, 0.0)
        )
        if cls is not None:
            reading = "defavorable" if share > 0.9 else "neutre"
            signals.append(
                Signal(
                    "concentration_classe",
                    "diversification",
                    "transversal",
                    "Classe d'actifs dominante",
                    reading,
                    f"La classe « {cls} » représente {_pct(share, 0)} du portefeuille"
                    + (
                        " : tout repose sur une seule classe d'actifs — les classes ne baissent pas toutes en même "
                        "temps, c'est ce qui rend la diversification gratuite"
                        if reading == "defavorable"
                        else ""
                    )
                    + ".",
                    _pct(share, 0),
                    "moyen",
                    "forte",
                    "allocation",
                )
            )
    if total > 0 and valued:
        foreign = sum(p.value_base for p in valued if p.currency != inp.base_currency) / total
        reading = "neutre"
        signals.append(
            Signal(
                "exposition_devises",
                "risque",
                "transversal",
                "Exposition aux devises étrangères",
                reading,
                f"{_pct(foreign, 0)} des positions sont cotées dans une autre devise que {inp.base_currency} : leur "
                "valeur "
                "bouge aussi avec le change, dans les deux sens. Ni bon ni mauvais — à savoir.",
                _pct(foreign, 0),
                "faible",
                "forte",
                "taux-de-change",
            )
        )
    cash_share = allocation.get("tresorerie", 0.0)
    if total > 0:
        signals.append(
            Signal(
                "tresorerie",
                "allocation",
                "transversal",
                "Part de trésorerie",
                "neutre",
                f"{_pct(cash_share, 0)} du portefeuille en liquidités"
                + (
                    " : une réserve importante non investie — elle protège des baisses et rate les hausses"
                    if cash_share > 0.3
                    else " : quasiment tout est investi — pas de coussin pour saisir une baisse ou faire face à un imprévu"
                    if cash_share < 0.02
                    else ""
                )
                + ".",
                _pct(cash_share, 0),
                "faible",
                "moyenne",
                "allocation",
            )
        )

    # --- correlation, volatility, drawdown -------------------------------------
    if inp.avg_correlation is not None and inp.correlation_pairs > 0:
        corr = inp.avg_correlation
        reading = "defavorable" if corr > 0.7 else "favorable" if corr < 0.4 else "neutre"
        signals.append(
            Signal(
                "correlation_moyenne",
                "diversification",
                "transversal",
                "Corrélation moyenne entre les lignes",
                reading,
                f"Corrélation moyenne de {_fmt(corr)} sur {inp.correlation_pairs} paire{_s(inp.correlation_pairs)}"
                + (
                    " : les lignes montent et baissent ensemble — beaucoup de titres, mais un seul pari"
                    if reading == "defavorable"
                    else " : les lignes évoluent de façon assez indépendante, ce qui lisse les à-coups"
                    if reading == "favorable"
                    else " : diversification moyenne"
                )
                + ".",
                _fmt(corr),
                "moyen",
                "forte",
                "correlation-diversification",
            )
        )
    if inp.volatility_annualized is not None:
        vol = inp.volatility_annualized
        level = "faible" if vol < 0.1 else "modérée" if vol < 0.2 else "élevée"
        signals.append(
            Signal(
                "volatilite_portefeuille",
                "risque",
                "transversal",
                "Volatilité du portefeuille",
                "neutre",
                f"Volatilité annualisée {level} : {_pct(vol)}. Repères : un portefeuille 100 % actions mondiales ~15 "
                "%, "
                "50/50 actions-obligations ~8 %, 100 % crypto > 60 %.",
                _pct(vol),
                "moyen",
                "forte",
                "volatilite-drawdown",
            )
        )
    if inp.max_drawdown is not None:
        signals.append(
            Signal(
                "drawdown_portefeuille",
                "risque",
                "transversal",
                "Pire repli du portefeuille",
                "neutre",
                f"Le portefeuille a perdu jusqu'à {_pct(inp.max_drawdown)} depuis un sommet sur la période analysée. "
                "Si ce chiffre vous aurait fait vendre en panique, le portefeuille est trop risqué pour vous — c'est "
                "la "
                "question la plus utile à se poser.",
                _pct(inp.max_drawdown),
                "moyen",
                "forte",
                "volatilite-drawdown",
            )
        )

    # --- big unrealized moves (informational) ------------------------------------
    for p in valued:
        if p.unrealized_pnl_pct is not None and abs(p.unrealized_pnl_pct) >= 0.3:
            up = p.unrealized_pnl_pct > 0
            signals.append(
                Signal(
                    f"latent_{p.symbol}",
                    "positions",
                    "transversal",
                    f"{p.symbol} : {'plus' if up else 'moins'}-value latente importante",
                    "neutre",
                    f"{p.symbol} affiche {_pct(p.unrealized_pnl_pct, 0)} par rapport à son coût d'achat. "
                    + (
                        "Une forte hausse gonfle mécaniquement le poids de la ligne (voir la concentration) ; le "
                        "prix d'achat n'est pas une raison de vendre ni de garder — seule compte la valeur d'aujourd'hui."
                        if up
                        else "Le prix d'achat n'est pas un niveau magique de retour : la question est si vous achèteriez ce titre aujourd'hui à ce prix, pas s'il « doit » remonter (biais d'aversion aux pertes)."
                    ),
                    _pct(p.unrealized_pnl_pct, 0),
                    "faible",
                    "forte",
                    "efficience-des-marches",
                )
            )

    # --- drift vs target allocation ---------------------------------------------
    drift: dict[str, float] = {}
    if inp.target_allocation and total > 0:
        for cls, target in inp.target_allocation.items():
            drift[cls] = allocation.get(cls, 0.0) - float(target)
        worst = max(drift.items(), key=lambda kv: abs(kv[1]), default=None)
        if worst is not None:
            cls, gap = worst
            reading = "defavorable" if abs(gap) > 0.10 else "neutre" if abs(gap) > 0.05 else "favorable"
            signals.append(
                Signal(
                    "ecart_cible",
                    "allocation",
                    "transversal",
                    "Écart à l'allocation cible",
                    reading,
                    f"Plus grand écart : « {cls} » à {_pct(allocation.get(cls, 0.0), 0)} contre "
                    f"{_pct(float(inp.target_allocation[cls]), 0)} visés "
                    f"({gap * 100:+.0f} points)"
                    + (
                        ". Au-delà de 10 points, le portefeuille ne ressemble plus au plan que vous vous étiez fixé "
                        ": c'est le moment où l'on rééquilibre d'habitude (en investissant les apports là où il manque, ou en arbitrant)"
                        if reading == "defavorable"
                        else ". Le portefeuille suit votre plan"
                        if reading == "favorable"
                        else ". Écart modéré : surveiller"
                    )
                    + ".",
                    f"{gap * 100:+.0f} pts",
                    "moyen",
                    "forte",
                    "allocation",
                )
            )
    if inp.missing_prices:
        signals.append(
            Signal(
                "prix_manquants",
                "donnees",
                "transversal",
                "Positions sans prix",
                "indisponible",
                f"{inp.missing_prices} position{_s(inp.missing_prices)} sans prix connu : elle{_s(inp.missing_prices)} "
                f"n'entre{'nt' if inp.missing_prices > 1 else ''} dans aucun des calculs ci-dessus.",
                str(inp.missing_prices),
                "faible",
                "forte",
                "fraicheur-des-donnees",
            )
        )

    t = tally(signals)
    if not valued:
        overall = "Aucune position valorisée : le bilan portera sur la diversification et le risque dès que le portefeuille contiendra des titres avec un prix."
    elif t.defavorable == 0:
        overall = (
            "Aucun point d'attention structurel : diversification et allocation dans les clous des repères habituels."
        )
    else:
        overall = f"{t.defavorable} point{'s' if t.defavorable > 1 else ''} d'attention (marqué{'s' if t.defavorable > 1 else ''} « défavorable »), {t.favorable} point{'s' if t.favorable > 1 else ''} fort{'s' if t.favorable > 1 else ''}. Les points d'attention portent sur la structure du portefeuille, pas sur les titres eux-mêmes."
    return PortfolioCheckup(signals=signals, tally=t, overall=overall, allocation=allocation, drift=drift)


# ---------------------------------------------------------------------------
# Buy / sell framing: verdicts, arguments, levels, holder view
# ---------------------------------------------------------------------------

ORIENTATIONS = ("achat", "vente", "attendre")
ORIENTATION_LABELS = {"achat": "Plutôt achat", "vente": "Plutôt vente", "attendre": "Attendre / observer"}
HOLDER_LABELS = {
    "achat": "Conserver, voire renforcer",
    "vente": "Alléger ou vendre",
    "attendre": "Conserver et surveiller",
}


@dataclass
class Verdict:
    horizon: str
    label: str
    orientation: str
    confidence: str  # faible | moyenne | forte
    text: str
    buy_case: list[str] = field(default_factory=list)
    sell_case: list[str] = field(default_factory=list)
    available: int = 0


def orientation_from_tally(t: Tally) -> tuple[str, str]:
    """Majority rule with a margin: at least two more readings one way, and
    a clear ratio. Returns (orientation, confidence)."""
    if t.available == 0:
        return "attendre", "faible"
    margin = t.favorable - t.defavorable
    if margin >= 2 and t.favorable >= 1.5 * max(t.defavorable, 1):
        orientation = "achat"
    elif margin <= -2 and t.defavorable >= 1.5 * max(t.favorable, 1):
        orientation = "vente"
    else:
        return "attendre", "moyenne" if t.available >= 3 else "faible"
    share = max(t.favorable, t.defavorable) / t.available
    confidence = "forte" if share >= 0.7 and t.available >= 5 else "moyenne" if t.available >= 3 else "faible"
    return orientation, confidence


def _short(signal: Signal) -> str:
    return f"{signal.label}" + (f" ({signal.value})" if signal.value else "")


def verdicts(signals: list[Signal]) -> list[Verdict]:
    out = []
    for horizon in ("court_terme", "long_terme"):
        subset = [s for s in signals if s.horizon == horizon]
        t = tally(subset)
        orientation, confidence = orientation_from_tally(t)
        label = "Court terme (semaines à mois)" if horizon == "court_terme" else "Long terme (années)"
        if t.available == 0:
            text = "Aucune lecture disponible pour cet horizon."
        elif orientation == "achat":
            text = (
                f"{t.favorable} méthode{_s(t.favorable)} sur {t.available} penche{'nt' if t.favorable > 1 else ''} "
                f"pour un achat, {t.defavorable} contre : les arguments à l'achat dominent (confiance {confidence})."
            )
        elif orientation == "vente":
            text = (
                f"{t.defavorable} méthode{_s(t.defavorable)} sur {t.available} penche{'nt' if t.defavorable > 1 else ''} "
                f"pour une vente ou une abstention, {t.favorable} pour un achat : les arguments à la vente dominent "
                f"(confiance {confidence})."
            )
        else:
            text = (
                f"{t.favorable} pour l'achat, {t.defavorable} pour la vente, {t.neutre} neutre{_s(t.neutre)} : "
                "pas de majorité nette — attendre un signal plus clair ou observer."
            )
        out.append(
            Verdict(
                horizon=horizon,
                label=label,
                orientation=orientation,
                confidence=confidence,
                text=text,
                buy_case=[_short(s) for s in subset if s.reading == "favorable"],
                sell_case=[_short(s) for s in subset if s.reading == "defavorable"],
                available=t.available,
            )
        )
    return out


def overall_orientation(vs: list[Verdict]) -> tuple[str, str, str]:
    """Combines the horizons: agreement → that orientation; disagreement →
    'attendre' with the explanation. Returns (orientation, confidence, text)."""
    court = next((v for v in vs if v.horizon == "court_terme"), None)
    long_ = next((v for v in vs if v.horizon == "long_terme"), None)
    have = [v for v in (court, long_) if v is not None and v.available > 0]
    if not have:
        return "attendre", "faible", "Pas assez de données pour se prononcer."
    if len(have) == 1:
        v = have[0]
        which = "court terme" if v.horizon == "court_terme" else "long terme"
        return (
            v.orientation,
            "faible" if v.confidence == "faible" else "moyenne",
            f"Seul le {which} est couvert : {ORIENTATION_LABELS[v.orientation].lower()} sur cet horizon. "
            + (
                "Les fondamentaux manquent (source non configurée ou instrument sans bilan)."
                if v.horizon == "court_terme"
                else ""
            ),
        )
    if court.orientation == long_.orientation:
        o = court.orientation
        conf = (
            "forte"
            if "forte" in (court.confidence, long_.confidence) and "faible" not in (court.confidence, long_.confidence)
            else "moyenne"
        )
        if o == "attendre":
            conf = "moyenne"
        return o, conf, f"Court et long terme concordent : {ORIENTATION_LABELS[o].lower()}."
    if "attendre" in (court.orientation, long_.orientation):
        decided = court if court.orientation != "attendre" else long_
        which = "court terme" if decided.horizon == "court_terme" else "long terme"
        other = "long terme" if which == "court terme" else "court terme"
        return (
            decided.orientation,
            "faible",
            f"Le {which} penche pour {ORIENTATION_LABELS[decided.orientation].lower().replace('plutôt ', '')} ; "
            f"le {other} ne tranche pas. Orientation faible : à confirmer.",
        )
    if court.orientation == "vente" and long_.orientation == "achat":
        return (
            "attendre",
            "moyenne",
            "Désaccord : les fondamentaux invitent à acheter mais la tendance est baissière — un investisseur "
            "long terme peut acheter progressivement, un trader attend le retournement de la tendance.",
        )
    return (
        "attendre",
        "moyenne",
        "Désaccord : la tendance est haussière mais les fondamentaux sont chers ou fragiles — un trader peut "
        "suivre l'élan avec un stop serré, un investisseur long terme attend un meilleur prix.",
    )


@dataclass
class Levels:
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
    method: str = (
        "stop de protection = cours − 2 × ATR(14) (au-delà du « bruit » normal) ; objectif = cours + 3 × ATR "
        "(ratio gain/risque 1,5) ; stop suiveur = plus haut des 20 derniers jours − 2 × ATR ; supports et "
        "résistances = creux et sommets locaux des 12 derniers mois regroupés à ±1,5 % ; taille de position = "
        "montant risqué (capital × % risqué) / (cours − stop)"
    )


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, window: int = 14) -> float | None:
    n = len(closes)
    if n < window + 1:
        return None
    prev = closes[:-1]
    tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - prev), np.abs(lows[1:] - prev)))
    return float(tr[-window:].mean())


def support_resistance(
    closes: np.ndarray, *, window: int = 5, tolerance: float = 0.015
) -> tuple[list[float], list[float]]:
    """Local extrema over `window` bars each side, clustered at ±tolerance;
    returns supports below and resistances above the last close, nearest
    first, at most three each."""
    n = len(closes)
    if n < 2 * window + 1:
        return [], []
    levels = []
    for i in range(window, n - window):
        seg = closes[i - window : i + window + 1]
        if closes[i] == seg.max() or closes[i] == seg.min():
            levels.append(float(closes[i]))
    levels.sort()
    clusters: list[list[float]] = []
    for level in levels:
        if clusters and abs(level - clusters[-1][-1]) / clusters[-1][-1] <= tolerance:
            clusters[-1].append(level)
        else:
            clusters.append([level])
    centers = [sum(c) / len(c) for c in clusters if len(c) >= 2] or [c[0] for c in clusters]
    price = float(closes[-1])
    supports = sorted([c for c in centers if c < price * 0.995], reverse=True)[:3]
    resistances = sorted([c for c in centers if c > price * 1.005])[:3]
    return supports, resistances


def compute_levels(closes, highs=None, lows=None, *, capital: float = 10_000.0, risk_pct: float = 1.0) -> Levels | None:
    c = quant._f(closes)
    if len(c) == 0:
        return None
    h = quant._f(highs) if highs is not None and len(highs) == len(c) else c
    lo = quant._f(lows) if lows is not None and len(lows) == len(c) else c
    price = float(c[-1])
    atr = _atr(h, lo, c)
    stop = price - 2 * atr if atr else None
    target = price + 3 * atr if atr else None
    year = c[-252:]
    trailing = float(c[-20:].max()) - 2 * atr if atr and len(c) >= 20 else None
    supports, resistances = support_resistance(year)
    risk_amount = capital * risk_pct / 100.0
    size = int(risk_amount // (price - stop)) if stop and price - stop > 0 else None
    return Levels(
        price=price,
        atr=atr,
        stop_loss=stop,
        stop_loss_pct=(stop / price - 1.0) if stop else None,
        target=target,
        target_pct=(target / price - 1.0) if target else None,
        risk_reward=((target - price) / (price - stop)) if stop and target and price - stop > 0 else None,
        trailing_stop=trailing,
        supports=supports,
        resistances=resistances,
        high_52w=float(year.max()) if len(year) else None,
        low_52w=float(year.min()) if len(year) else None,
        position_size=size,
        capital=capital,
        risk_pct=risk_pct,
        risk_amount=risk_amount,
    )


@dataclass
class HolderView:
    entry_price: float | None
    pnl_pct: float | None
    orientation: str
    label: str
    text: str
    below_stop: bool | None


def holder_view(orientation: str, levels: Levels | None, entry_price: float | None) -> HolderView:
    price = levels.price if levels else None
    pnl = (price / entry_price - 1.0) if price and entry_price else None
    below = (price < levels.trailing_stop) if levels and levels.trailing_stop and price else None
    label = HOLDER_LABELS[orientation]
    if orientation == "achat":
        text = "Les méthodes qui justifieraient un achat justifient aussi de conserver."
    elif orientation == "vente":
        text = "Les méthodes penchent contre le titre : alléger ou vendre est la lecture manuel — le prix d'achat n'y change rien."
    else:
        text = "Pas de signal net : conserver en surveillant le stop suiveur."
    if pnl is not None:
        text += f" Depuis votre entrée : {pnl * 100:+.1f} %."
        if pnl < -0.3:
            text += " Une perte de plus de 30 % ne se « rattrape » pas mécaniquement : la question est si vous achèteriez aujourd'hui à ce prix."
    if below:
        text += " Le cours est passé sous le stop suiveur : la tendance qui justifiait la position s'est retournée."
    return HolderView(entry_price, pnl, orientation, label, text, below)


# ---------------------------------------------------------------------------
# Past validation of the technical readings ("quand ce bilan disait achat…")
# ---------------------------------------------------------------------------


@dataclass
class OrientationStats:
    orientation: str
    label: str
    count: int
    mean_return: float | None
    median_return: float | None
    hit_rate: float | None  # share of cases where the orientation was "right"
    worst: float | None
    best: float | None


@dataclass
class PastValidation:
    horizon_days: int
    evaluations: int
    start: object | None
    end: object | None
    by_orientation: list[OrientationStats]
    baseline_mean_return: float | None
    baseline_hit_rate: float | None
    timeline: list[tuple]  # (date, orientation, close)
    text: str
    method: str = (
        "à chaque date passée, les lectures techniques sont recalculées avec les seules données antérieures "
        "(aucune fuite du futur) et l'orientation court terme en est déduite ; on mesure ensuite le rendement "
        "réalisé sur l'horizon suivant. Référence : toutes les dates confondues (acheter n'importe quand)"
    )


def past_validation(
    dates: list, closes, *, horizon_days: int = 20, min_history: int = 274, max_points: int = 400
) -> PastValidation:
    c = quant._f(closes)
    n = len(c)
    usable = list(range(min_history, n - horizon_days))
    if len(usable) > max_points:
        step = math.ceil(len(usable) / max_points)
        usable = usable[::step]
    rows: list[tuple[object, str, float, float]] = []
    for i in usable:
        signals = [s for s in technical_signals(c[: i + 1]) if s.horizon == "court_terme"]
        orientation, _ = orientation_from_tally(tally(signals))
        fwd = c[i + horizon_days] / c[i] - 1.0 if c[i] > 0 else float("nan")
        if math.isfinite(fwd):
            rows.append((dates[i], orientation, float(c[i]), fwd))
    by = []
    for o in ORIENTATIONS:
        r = np.array([x[3] for x in rows if x[1] == o])
        if len(r) == 0:
            by.append(OrientationStats(o, ORIENTATION_LABELS[o], 0, None, None, None, None, None))
            continue
        hit = float((r > 0).mean()) if o != "vente" else float((r < 0).mean())
        by.append(
            OrientationStats(
                o,
                ORIENTATION_LABELS[o],
                len(r),
                float(r.mean()),
                float(np.median(r)),
                hit,
                float(r.min()),
                float(r.max()),
            )
        )
    all_r = np.array([x[3] for x in rows])
    base_mean = float(all_r.mean()) if len(all_r) else None
    base_hit = float((all_r > 0).mean()) if len(all_r) else None
    achat = next(b for b in by if b.orientation == "achat")
    vente = next(b for b in by if b.orientation == "vente")
    if not rows:
        text = (
            "Pas assez d'historique pour tester la méthode sur le passé (il faut plus d'un an de cours plus l'horizon)."
        )
    else:
        parts = [f"Sur {len(rows)} dates passées, horizon {horizon_days} jours."]
        if achat.count:
            parts.append(
                f"Quand le bilan court terme disait « achat » ({achat.count} fois), le cours était plus haut "
                f"{horizon_days} jours après dans {achat.hit_rate * 100:.0f} % des cas (rendement moyen {achat.mean_return * 100:+.1f} %)."
            )
        if vente.count:
            parts.append(
                f"Quand il disait « vente » ({vente.count} fois), le cours était plus bas ensuite dans "
                f"{vente.hit_rate * 100:.0f} % des cas (rendement moyen {vente.mean_return * 100:+.1f} %)."
            )
        if base_hit is not None:
            parts.append(
                f"Référence acheter n'importe quand : hausse dans {base_hit * 100:.0f} % des cas, {base_mean * 100:+.1f} % en moyenne."
            )
        edge = achat.hit_rate is not None and base_hit is not None and achat.hit_rate > base_hit + 0.05
        parts.append(
            "Sur ce titre et cette période, la méthode a apporté un avantage par rapport au hasard."
            if edge
            else "Sur ce titre et cette période, la méthode n'a pas fait mieux que d'acheter n'importe quand — ce qui est le résultat le plus fréquent, et une leçon en soi."
        )
        text = " ".join(parts)
    return PastValidation(
        horizon_days=horizon_days,
        evaluations=len(rows),
        start=rows[0][0] if rows else None,
        end=rows[-1][0] if rows else None,
        by_orientation=by,
        baseline_mean_return=base_mean,
        baseline_hit_rate=base_hit,
        timeline=[(d, o, close) for d, o, close, _ in rows],
        text=text,
    )
