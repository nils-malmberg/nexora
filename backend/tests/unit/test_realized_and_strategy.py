"""Pure-domain checks: FIFO sale matching, strategy study mechanics
(no look-ahead, fees, benchmark) and rebasing."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from app.domain import quant
from app.domain.positions import SaleMatch, replay_lots
from app.models import Transaction


def _tx(type_, day, qty, price, fees="0", currency="EUR", tx_id=None):
    return Transaction(
        id=tx_id or f"{type_}-{day}",
        portfolio_id="p",
        instrument_id="i",
        type=type_,
        trade_date=datetime(2026, 1, day, tzinfo=UTC),
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        currency=currency,
        fees=Decimal(fees),
    )


def test_fifo_sale_matching_records_consumed_lots():
    txs = [_tx("achat", 1, "10", "100", "5"), _tx("achat", 2, "10", "120"), _tx("vente", 3, "15", "130", "2")]
    sales: list[SaleMatch] = []
    lots = replay_lots(txs, sales)
    assert len(sales) == 1
    match = sales[0]
    assert [(c.quantity, c.unit_cost) for c in match.consumptions] == [
        (Decimal("10"), Decimal("100.500000")),  # 100 + 5/10 fees per share
        (Decimal("5"), Decimal("120.000000")),
    ]
    assert lots[0].quantity_remaining == Decimal("5")
    # Without the collector the replay is unchanged (single implementation).
    assert replay_lots(txs)[0].quantity_remaining == Decimal("5")


def test_split_before_sale_adjusts_consumed_cost():
    txs = [_tx("achat", 1, "10", "100"), _tx("split", 2, "2", "0"), _tx("vente", 3, "20", "60")]
    sales: list[SaleMatch] = []
    replay_lots(txs, sales)
    (c,) = sales[0].consumptions
    assert (c.quantity, c.unit_cost) == (Decimal("20"), Decimal("50"))


def _series(n=400, seed=1):
    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    return dates, closes


def test_strategy_signal_is_applied_next_day_no_look_ahead():
    dates, closes = _series()
    study = quant.strategy_study(dates, closes, "sma_cross", fast=5, slow=20, fee_bps=0)
    assert study.has_sufficient_data
    # Recompute independently: position for day t's return is the signal of t-1.
    fast = quant._sma_f(closes, 5)
    slow = quant._sma_f(closes, 20)
    signal = np.where(np.isnan(fast) | np.isnan(slow), 0, (fast > slow).astype(int))
    equity = 1.0
    for t in range(1, len(closes)):
        equity *= 1 + signal[t - 1] * (closes[t] / closes[t - 1] - 1)
    assert study.strategy_equity[-1] == pytest.approx(equity, rel=1e-9)
    assert study.benchmark_equity[-1] == pytest.approx(closes[-1] / closes[0])
    assert 0 < study.exposure_share < 1
    assert study.n_trades >= 1


def test_strategy_fees_reduce_equity_and_rules_validate():
    dates, closes = _series()
    free = quant.strategy_study(dates, closes, "price_above_sma", slow=30, fee_bps=0)
    paid = quant.strategy_study(dates, closes, "price_above_sma", slow=30, fee_bps=50)
    assert paid.strategy_equity[-1] < free.strategy_equity[-1]
    assert paid.n_trades == free.n_trades
    rsi = quant.strategy_study(dates, closes, "rsi_reversion", rsi_period=14, rsi_low=35, rsi_high=65)
    assert rsi.has_sufficient_data and rsi.strategy_stats is not None
    assert not quant.strategy_study(dates[:50], closes[:50], "sma_cross").has_sufficient_data
    assert not quant.strategy_study(dates, closes, "sma_cross", fast=50, slow=20).has_sufficient_data
    with pytest.raises(ValueError):
        quant.strategy_study(dates, closes, "martingale")


def test_always_in_rule_matches_buy_and_hold_after_warmup():
    """A rule that is invested every day after warm-up must track the
    benchmark from that day on (the mechanics add nothing on their own)."""
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(200)]
    closes = np.linspace(100, 200, 200)  # monotonic: price is always above its SMA
    study = quant.strategy_study(dates, closes, "price_above_sma", slow=10, fee_bps=0)
    first_signal = 9  # SMA(10) exists from index 9: entered at that close, first return captured on day 10
    expected = closes[-1] / closes[first_signal]
    assert study.strategy_equity[-1] == pytest.approx(expected, rel=1e-9)


def test_rebase_series_uses_common_dates_only():
    d = [date(2024, 1, 1) + timedelta(days=i) for i in range(5)]
    a = list(zip(d, [10, 11, 12, 13, 14], strict=True))
    b = list(zip(d[1:], [200, 220, 200, 100], strict=True))
    dates, rebased = quant.rebase_series({"a": a, "b": b})
    assert dates == d[1:]
    assert rebased["a"][0] == 100 and rebased["b"][0] == 100
    assert rebased["b"][-1] == pytest.approx(50)
    assert rebased["a"][-1] == pytest.approx(14 / 11 * 100)
