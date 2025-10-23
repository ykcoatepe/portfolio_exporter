from __future__ import annotations

from decimal import Decimal

from positions_engine.combos.detector import OptionCombo, OptionLegSnapshot
from positions_engine.combos.eval import _evaluate_combo
from positions_engine.combos.taxonomy import ComboStrategy


def _make_leg(*, leg_id: str, quantity: str, strike: str) -> OptionLegSnapshot:
    qty = Decimal(quantity)
    return OptionLegSnapshot(
        leg_id=leg_id,
        instrument_symbol="SPY",
        account="ACC",
        underlying="SPY",
        expiry="2025-01-17",
        dte=30,
        right="CALL",
        strike=Decimal(strike),
        quantity=qty,
        ratio=Decimal("1"),
        multiplier=Decimal("100"),
        avg_cost=Decimal("1"),
        mark=Decimal("0"),
        mark_source="MID",
        stale_seconds=None,
        previous_close=None,
        delta=None,
        gamma=None,
        theta=None,
        vega=None,
        iv=None,
        day_pnl=Decimal("0"),
        total_pnl=Decimal("0"),
        day_basis=None,
        total_basis=None,
    )


def _make_combo(*, total_pnl: Decimal) -> OptionCombo:
    short_leg = _make_leg(leg_id="short", quantity="-1", strike="450")
    long_leg = _make_leg(leg_id="long", quantity="1", strike="455")
    return OptionCombo(
        combo_id="combo",
        strategy=ComboStrategy.VERTICAL,
        account="ACC",
        underlying="SPY",
        dte=30,
        net_price=Decimal("-1.00"),
        sum_delta=Decimal("0"),
        sum_gamma=Decimal("0"),
        sum_theta=Decimal("0"),
        sum_vega=Decimal("0"),
        day_pnl=Decimal("0"),
        total_pnl=total_pnl,
        day_pnl_percent=None,
        total_pnl_percent=None,
        legs=(short_leg, long_leg),
    )


def test_credit_combo_tp_done_sets_exit_as_unit() -> None:
    combo = _make_combo(total_pnl=Decimal("65"))
    payload = _evaluate_combo(combo, Decimal("0.40"), Decimal("0.60"))

    assert payload["tp_done"] is True
    assert payload["exit_as_unit"] is True


def test_credit_combo_stop_sets_exit_as_unit() -> None:
    combo = _make_combo(total_pnl=Decimal("-450"))
    payload = _evaluate_combo(combo, Decimal("0.40"), Decimal("0.60"))

    assert payload["sl_hit"] is True
    assert payload["exit_as_unit"] is True
    assert payload["tp_done"] is False


def test_debit_combo_tp_done_sets_exit_as_unit() -> None:
    short_leg = _make_leg(leg_id="short", quantity="-1", strike="450")
    long_leg = _make_leg(leg_id="long", quantity="1", strike="445")
    combo = OptionCombo(
        combo_id="combo-debit",
        strategy=ComboStrategy.VERTICAL,
        account="ACC",
        underlying="SPY",
        dte=30,
        net_price=Decimal("1.00"),
        sum_delta=Decimal("0"),
        sum_gamma=Decimal("0"),
        sum_theta=Decimal("0"),
        sum_vega=Decimal("0"),
        day_pnl=Decimal("0"),
        total_pnl=Decimal("200"),
        day_pnl_percent=None,
        total_pnl_percent=None,
        legs=(short_leg, long_leg),
    )

    payload = _evaluate_combo(combo, Decimal("0.40"), Decimal("0.60"))

    assert payload["tp_done"] is True
    assert payload["exit_as_unit"] is True
