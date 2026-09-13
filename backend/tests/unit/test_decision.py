"""Decision aid: each reading follows its textbook rule, missing data is
`indisponible` (never a guess), and the summary is a tally, not a verdict."""

from __future__ import annotations

import numpy as np
import pytest

from app.domain import decision


def _keyed(signals):
    return {s.key: s for s in signals}


def test_short_series_yields_unavailable_readings_only():
    signals = _keyed(decision.technical_signals([100.0, 101.0, 102.0]))
    assert signals["tendance_sma"].reading == "indisponible"
    assert signals["rsi"].reading == "indisponible"
    assert "300 clôtures" not in signals["rsi"].detail and "30 clôtures" in signals["rsi"].detail
    aid = decision.summarize_instrument(list(signals.values()))
    assert aid.tally.available == 0 and "Pas assez de données" in aid.overall


def test_uptrend_reads_favorable_and_downtrend_defavorable():
    up = np.linspace(50, 150, 300)
    s = _keyed(decision.technical_signals(up))
    assert s["tendance_sma"].reading == "favorable" and s["croisement_sma"].reading == "favorable"
    assert s["momentum_12_1"].reading == "favorable" and s["macd"].reading == "favorable"
    assert s["plus_haut_52s"].reading == "favorable"  # within 5 % of the 52-week high
    assert s["rsi"].reading == "defavorable"  # a straight line up is "overbought"
    assert s["sharpe_1a"].reading == "favorable"
    down = np.linspace(150, 50, 300)
    d = _keyed(decision.technical_signals(down))
    assert d["tendance_sma"].reading == "defavorable" and d["croisement_sma"].reading == "defavorable"
    assert d["momentum_12_1"].reading == "defavorable" and d["rsi"].reading == "favorable"
    assert d["sharpe_1a"].reading == "defavorable"
    for sig in list(s.values()) + list(d.values()):
        assert sig.reading in decision.READINGS and sig.detail and sig.evidence in ("forte", "moyenne", "faible")


def test_risk_readings_are_informational():
    rng = np.random.default_rng(0)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, 300)))
    s = _keyed(decision.technical_signals(closes))
    assert s["volatilite"].reading == "neutre" and "élevée" in s["volatilite"].detail
    assert s["drawdown_1a"].reading == "neutre" and s["drawdown_1a"].value.startswith("-")


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"pe": "12"}, "favorable"),
        ({"pe": "20"}, "neutre"),
        ({"pe": "40"}, "defavorable"),
        ({"pe": "-5"}, "defavorable"),
        ({}, "indisponible"),
    ],
)
def test_pe_thresholds(data, expected):
    assert _keyed(decision.fundamental_signals(data))["per"].reading == expected


def test_fundamental_readings_cover_quality_and_consensus():
    good = _keyed(
        decision.fundamental_signals(
            {
                "pb": "1.2",
                "dividend_yield": "0.04",
                "eps_growth": "0.2",
                "roe": "0.2",
                "net_margin": "0.15",
                "debt_to_equity": "0.3",
                "beta": "0.7",
                "analyst_buy": 8,
                "analyst_hold": 2,
                "analyst_sell": 0,
            }
        )
    )
    for key in ("pb", "rendement_dividende", "croissance_bpa", "roe", "marge_nette", "dette", "consensus_analystes"):
        assert good[key].reading == "favorable", key
    assert good["beta"].reading == "neutre" and "défensif" in good["beta"].detail
    bad = _keyed(
        decision.fundamental_signals(
            {
                "pb": "9",
                "eps_growth": "-0.1",
                "roe": "0.01",
                "net_margin": "-0.05",
                "debt_to_equity": "3",
                "analyst_buy": 1,
                "analyst_hold": 2,
                "analyst_sell": 3,
            }
        )
    )
    for key in ("pb", "croissance_bpa", "roe", "marge_nette", "dette", "consensus_analystes"):
        assert bad[key].reading == "defavorable", key
    assert bad["per"].reading == "indisponible" and bad["rendement_dividende"].reading == "indisponible"
    assert _keyed(decision.fundamental_signals({"pe": "abc"}))["per"].reading == "indisponible"


def test_prediction_signal_requires_out_of_sample_edge():
    metrics_good = {"meta": {"direction_accuracy": 0.6, "mae": 0.01}, "naive": {"mae": 0.02}}
    metrics_bad = {"meta": {"direction_accuracy": 0.5, "mae": 0.03}, "naive": {"mae": 0.02}}
    up = decision.prediction_signal({"expected_log_return": 0.02}, metrics_good, 5)
    assert up.reading == "favorable" and "5 j" in up.label and up.value == "2.0 %"
    down = decision.prediction_signal({"expected_log_return": -0.02}, metrics_good, 5)
    assert down.reading == "defavorable"
    weak = decision.prediction_signal({"expected_log_return": 0.05}, metrics_bad, 5)
    assert weak.reading == "neutre" and "à ignorer" in weak.detail
    assert decision.prediction_signal(None, metrics_good, 5) is None
    assert decision.prediction_signal({"expected_log_return": "x"}, metrics_good, 5) is None


def test_summary_detects_contradiction_between_horizons():
    signals = [
        decision.Signal("a", "tendance", "court_terme", "A", "favorable", ""),
        decision.Signal("b", "momentum", "court_terme", "B", "favorable", ""),
        decision.Signal("c", "valorisation", "long_terme", "C", "defavorable", ""),
        decision.Signal("d", "qualite", "long_terme", "D", "defavorable", ""),
        decision.Signal("e", "risque", "transversal", "E", "neutre", ""),
        decision.Signal("f", "risque", "transversal", "F", "indisponible", ""),
    ]
    aid = decision.summarize_instrument(signals)
    assert (aid.tally.favorable, aid.tally.defavorable, aid.tally.neutre, aid.tally.indisponible) == (2, 2, 1, 1)
    assert "porté par l'élan" in aid.overall
    court = next(h for h in aid.horizons if h.horizon == "court_terme")
    assert "penchent plutôt du côté favorable" in court.text
    assert "1 indisponible" in next(h for h in aid.horizons if h.horizon == "transversal").text


def _pos(symbol, value, cls="action", ccy="EUR", pnl=None):
    return decision.PositionInput(symbol, cls, ccy, value, pnl)


def test_portfolio_checkup_flags_concentration_and_drift():
    inp = decision.CheckupInput(
        base_currency="EUR",
        positions=[_pos("BIG", 700, pnl=0.5), _pos("SMALL", 200, ccy="USD", pnl=-0.4)],
        cash_base=100,
        total_base=1000,
        target_allocation={"action": 0.6, "tresorerie": 0.4},
        avg_correlation=0.85,
        correlation_pairs=1,
        volatility_annualized=0.25,
        max_drawdown=-0.3,
        missing_prices=1,
    )
    chk = decision.portfolio_checkup(inp)
    s = _keyed(chk.signals)
    assert s["concentration_instrument"].reading == "defavorable" and "BIG" in s["concentration_instrument"].detail
    assert s["nombre_lignes"].reading == "defavorable"
    assert s["concentration_classe"].reading == "neutre"  # 90 % is not > 90 %
    assert s["exposition_devises"].value == "20 %"
    assert s["correlation_moyenne"].reading == "defavorable"
    assert s["ecart_cible"].reading == "defavorable" and chk.drift["action"] == pytest.approx(0.3)
    assert s["latent_BIG"].reading == "neutre" and s["latent_SMALL"].reading == "neutre"
    assert s["prix_manquants"].reading == "indisponible"
    assert chk.allocation["action"] == pytest.approx(0.9) and chk.allocation["tresorerie"] == pytest.approx(0.1)
    assert "point" in chk.overall and chk.tally.defavorable >= 4


def test_portfolio_checkup_well_diversified_and_empty():
    positions = [_pos(f"P{i}", 100) for i in range(12)]
    chk = decision.portfolio_checkup(
        decision.CheckupInput("EUR", positions, 200, 1400, {"action": 0.86, "tresorerie": 0.14}, 0.3, 66, 0.12, -0.1)
    )
    s = _keyed(chk.signals)
    assert s["concentration_instrument"].reading == "favorable" and s["nombre_lignes"].reading == "favorable"
    assert s["correlation_moyenne"].reading == "favorable" and s["ecart_cible"].reading == "favorable"
    assert chk.tally.defavorable == 0 and "Aucun point d'attention" in chk.overall
    empty = decision.portfolio_checkup(decision.CheckupInput("EUR", [], 0, 0))
    assert (
        "Aucune position valorisée" in empty.overall and _keyed(empty.signals)["nombre_lignes"].reading == "defavorable"
    )


def test_orientation_rule_needs_margin_and_ratio():
    T = decision.Tally
    assert decision.orientation_from_tally(T(favorable=5, defavorable=1, neutre=1)) == ("achat", "forte")
    assert decision.orientation_from_tally(T(favorable=1, defavorable=4, neutre=2)) == ("vente", "moyenne")
    assert decision.orientation_from_tally(T(favorable=3, defavorable=2, neutre=0))[0] == "attendre"
    assert decision.orientation_from_tally(T(favorable=2, defavorable=0, neutre=0)) == ("achat", "faible")
    assert decision.orientation_from_tally(T()) == ("attendre", "faible")


def test_overall_orientation_explains_disagreement():
    up = [decision.Signal(f"a{i}", "tendance", "court_terme", "A", "favorable", "") for i in range(4)]
    cheap = [decision.Signal(f"b{i}", "valorisation", "long_terme", "B", "defavorable", "") for i in range(4)]
    o, conf, text = decision.overall_orientation(decision.verdicts(up + cheap))
    assert o == "attendre" and "Désaccord" in text
    o, conf, text = decision.overall_orientation(decision.verdicts(up))
    assert o == "achat" and "Seul le court terme" in text
    vs = decision.verdicts(
        up + [decision.Signal(f"c{i}", "qualite", "long_terme", "C", "favorable", "") for i in range(3)]
    )
    assert decision.overall_orientation(vs)[0] == "achat" and "concordent" in decision.overall_orientation(vs)[2]
    court = next(v for v in vs if v.horizon == "court_terme")
    assert len(court.buy_case) == 4 and court.sell_case == []


def test_levels_and_support_resistance():
    closes = np.array([100 + 10 * np.sin(i / 8) for i in range(300)])
    highs, lows = closes * 1.01, closes * 0.99
    lv = decision.compute_levels(closes, highs, lows, capital=20_000, risk_pct=0.5)
    assert lv.atr > 0 and lv.stop_loss < lv.price < lv.target
    assert lv.risk_reward == pytest.approx(1.5)
    assert lv.position_size == int(100 // (lv.price - lv.stop_loss))
    assert all(s < lv.price for s in lv.supports) and all(r > lv.price for r in lv.resistances)
    assert lv.high_52w >= lv.price >= lv.low_52w
    assert decision.compute_levels([]) is None
    supports, resistances = decision.support_resistance(np.array([1.0, 2.0]))
    assert supports == [] and resistances == []


def test_holder_view_mentions_entry_and_stop():
    lv = decision.compute_levels(np.linspace(100, 80, 60), np.linspace(101, 81, 60), np.linspace(99, 79, 60))
    hv = decision.holder_view("vente", lv, 120.0)
    assert hv.pnl_pct == pytest.approx(80 / 120 - 1) and "ne se « rattrape » pas" in hv.text
    assert hv.below_stop is True and "stop suiveur" in hv.text
    assert decision.holder_view("achat", None, None).pnl_pct is None
