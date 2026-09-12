from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.positions import cash_delta, freshness_status, replay_lots
from app.models import PricePoint, Transaction


def make_tx(**overrides) -> Transaction:
    defaults = dict(
        id="tx-1",
        type="achat",
        trade_date=datetime(2026, 1, 1, tzinfo=UTC),
        quantity=Decimal("10"),
        unit_price=Decimal("100"),
        currency="EUR",
        fees=Decimal("0"),
    )
    defaults.update(overrides)
    return Transaction(**defaults)


def test_cash_delta_achat_is_negative_price_plus_fees():
    tx = make_tx(type="achat", quantity=Decimal("10"), unit_price=Decimal("100"), fees=Decimal("5"))
    assert cash_delta(tx) == Decimal("-1005")


def test_cash_delta_vente_is_positive_minus_fees():
    tx = make_tx(type="vente", quantity=Decimal("10"), unit_price=Decimal("100"), fees=Decimal("5"))
    assert cash_delta(tx) == Decimal("995")


def test_cash_delta_depot_uses_unit_price_as_amount():
    tx = make_tx(type="depot", instrument_id=None, quantity=Decimal("1"), unit_price=Decimal("500"))
    assert cash_delta(tx) == Decimal("500")


def test_cash_delta_retrait_is_negative():
    tx = make_tx(type="retrait", instrument_id=None, quantity=Decimal("1"), unit_price=Decimal("200"))
    assert cash_delta(tx) == Decimal("-200")


def test_cash_delta_dividende_has_no_lot_effect_but_credits_cash():
    tx = make_tx(type="dividende", quantity=Decimal("1"), unit_price=Decimal("42"))
    assert cash_delta(tx) == Decimal("42")


def test_replay_lots_single_buy():
    lots = replay_lots([make_tx(type="achat", quantity=Decimal("10"), unit_price=Decimal("100"))])
    assert len(lots) == 1
    assert lots[0].quantity_remaining == Decimal("10")
    assert lots[0].unit_cost == Decimal("100")


def test_replay_lots_buy_includes_fees_in_cost_basis():
    lots = replay_lots([make_tx(type="achat", quantity=Decimal("10"), unit_price=Decimal("100"), fees=Decimal("10"))])
    # (10*100 + 10) / 10 = 101
    assert lots[0].unit_cost == Decimal("101")


def test_replay_lots_fifo_sell_consumes_oldest_lot_first():
    txs = [
        make_tx(
            id="t1",
            type="achat",
            trade_date=datetime(2026, 1, 1, tzinfo=UTC),
            quantity=Decimal("10"),
            unit_price=Decimal("100"),
        ),
        make_tx(
            id="t2",
            type="achat",
            trade_date=datetime(2026, 2, 1, tzinfo=UTC),
            quantity=Decimal("5"),
            unit_price=Decimal("200"),
        ),
        make_tx(
            id="t3",
            type="vente",
            trade_date=datetime(2026, 3, 1, tzinfo=UTC),
            quantity=Decimal("12"),
            unit_price=Decimal("150"),
        ),
    ]
    lots = replay_lots(txs)
    assert len(lots) == 1
    assert lots[0].source_transaction_id == "t2"
    assert lots[0].quantity_remaining == Decimal("3")


def test_replay_lots_oversell_raises():
    txs = [
        make_tx(id="t1", type="achat", quantity=Decimal("5"), unit_price=Decimal("100")),
        make_tx(id="t2", type="vente", quantity=Decimal("10"), unit_price=Decimal("100")),
    ]
    with pytest.raises(ValueError, match="exceeds available position"):
        replay_lots(txs)


def test_replay_lots_split_multiplies_quantity_and_divides_cost():
    txs = [
        make_tx(id="t1", type="achat", quantity=Decimal("10"), unit_price=Decimal("100")),
        make_tx(id="t2", type="split", quantity=Decimal("2")),
    ]
    lots = replay_lots(txs)
    assert lots[0].quantity_remaining == Decimal("20")
    assert lots[0].unit_cost == Decimal("50")


def test_freshness_status_missing():
    assert freshness_status(None) == "manquant"


def test_freshness_status_estimate():
    price = PricePoint(as_of=datetime.now(UTC), price=Decimal("1"), currency="EUR", is_estimate=True)
    assert freshness_status(price) == "estime"


def test_freshness_status_fresh_vs_stale():
    fresh = PricePoint(as_of=datetime.now(UTC), price=Decimal("1"), currency="EUR", is_estimate=False)
    assert freshness_status(fresh) == "a_jour"

    from datetime import timedelta

    stale = PricePoint(
        as_of=datetime.now(UTC) - timedelta(days=10), price=Decimal("1"), currency="EUR", is_estimate=False
    )
    assert freshness_status(stale) == "differe"
