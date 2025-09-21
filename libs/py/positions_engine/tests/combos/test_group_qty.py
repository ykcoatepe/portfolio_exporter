from __future__ import annotations

from decimal import Decimal

from positions_engine.combos import (
    ComboStrategy,
    OptionCombo,
    OptionLegSnapshot,
    group_option_combos,
)


def _make_leg(
    *,
    leg_id: str,
    symbol: str,
    underlying: str,
    expiry: str,
    dte: int,
    right: str,
    strike: str,
    quantity: str,
    avg_cost: str,
    mark: str,
    mark_source: str,
    stale_seconds: int,
    delta: str,
    gamma: str,
    theta: str,
    vega: str,
) -> OptionLegSnapshot:
    qty = Decimal(quantity)
    return OptionLegSnapshot(
        leg_id=leg_id,
        instrument_symbol=symbol,
        account="acct-test",
        underlying=underlying,
        expiry=expiry,
        dte=dte,
        right=right,
        strike=Decimal(strike),
        quantity=qty,
        ratio=abs(qty) or Decimal("1"),
        multiplier=Decimal("100"),
        avg_cost=Decimal(avg_cost),
        mark=Decimal(mark),
        mark_source=mark_source,
        stale_seconds=stale_seconds,
        previous_close=None,
        delta=Decimal(delta),
        gamma=Decimal(gamma),
        theta=Decimal(theta),
        vega=Decimal(vega),
        iv=None,
        day_pnl=Decimal("0"),
        total_pnl=Decimal("0"),
        day_basis=None,
        total_basis=None,
        notes=tuple(),
    )


def _make_combo(
    *,
    combo_id: str,
    strategy: ComboStrategy,
    underlying: str,
    dte: int,
    net_price: str,
    delta: str,
    gamma: str,
    theta: str,
    vega: str,
    legs: tuple[OptionLegSnapshot, ...],
) -> OptionCombo:
    return OptionCombo(
        combo_id=combo_id,
        strategy=strategy,
        account="acct-test",
        underlying=underlying,
        dte=dte,
        net_price=Decimal(net_price),
        sum_delta=Decimal(delta),
        sum_gamma=Decimal(gamma),
        sum_theta=Decimal(theta),
        sum_vega=Decimal(vega),
        day_pnl=Decimal("0"),
        total_pnl=Decimal("0"),
        day_pnl_percent=None,
        total_pnl_percent=None,
        legs=legs,
        notes=tuple(),
    )


def _build_vertical(combo_id: str, net_price: str) -> OptionCombo:
    debit = Decimal(net_price) < 0
    lower_qty = "1" if debit else "-1"
    upper_qty = "-1" if debit else "1"

    lower = _make_leg(
        leg_id=f"{combo_id}-lower",
        symbol="MSFT 20240517C00315000",
        underlying="MSFT",
        expiry="2024-05-17",
        dte=30,
        right="CALL",
        strike="315",
        quantity=lower_qty,
        avg_cost="2.10",
        mark="2.00",
        mark_source="MID",
        stale_seconds=45,
        delta="0.40" if debit else "-0.40",
        gamma="0.02",
        theta="-0.18" if debit else "0.18",
        vega="2.5" if debit else "-2.5",
    )
    upper = _make_leg(
        leg_id=f"{combo_id}-upper",
        symbol="MSFT 20240517C00320000",
        underlying="MSFT",
        expiry="2024-05-17",
        dte=30,
        right="CALL",
        strike="320",
        quantity=upper_qty,
        avg_cost="1.40",
        mark="1.35",
        mark_source="MID",
        stale_seconds=45,
        delta="-0.30" if debit else "0.30",
        gamma="-0.02",
        theta="0.16" if debit else "-0.16",
        vega="-2.0" if debit else "2.0",
    )

    combo = _make_combo(
        combo_id=combo_id,
        strategy=ComboStrategy.VERTICAL,
        underlying="MSFT",
        dte=30,
        net_price=net_price,
        delta="0.0",
        gamma="0.0",
        theta="0.0",
        vega="0.0",
        legs=(lower, upper),
    )
    return combo


def _build_condor(combo_id: str, net_price: str) -> OptionCombo:
    short = Decimal(net_price) > 0
    signs = (-1, 1, -1, 1) if short else (1, -1, 1, -1)
    legs = (
        _make_leg(
            leg_id=f"{combo_id}-put-short",
            symbol="SPY 20251018P00395000",
            underlying="SPY",
            expiry="2025-10-18",
            dte=45,
            right="PUT",
            strike="395",
            quantity=str(signs[0]),
            avg_cost="1.60",
            mark="1.55",
            mark_source="MID",
            stale_seconds=120,
            delta="-0.20" if short else "0.20",
            gamma="0.01",
            theta="-0.35" if short else "0.35",
            vega="-3.0" if short else "3.0",
        ),
        _make_leg(
            leg_id=f"{combo_id}-put-long",
            symbol="SPY 20251018P00400000",
            underlying="SPY",
            expiry="2025-10-18",
            dte=45,
            right="PUT",
            strike="400",
            quantity=str(signs[1]),
            avg_cost="0.40",
            mark="0.38",
            mark_source="MID",
            stale_seconds=120,
            delta="0.12" if short else "-0.12",
            gamma="-0.01",
            theta="0.18" if short else "-0.18",
            vega="1.6" if short else "-1.6",
        ),
        _make_leg(
            leg_id=f"{combo_id}-call-short",
            symbol="SPY 20251018C00440000",
            underlying="SPY",
            expiry="2025-10-18",
            dte=45,
            right="CALL",
            strike="440",
            quantity=str(signs[2]),
            avg_cost="1.10",
            mark="1.05",
            mark_source="MID",
            stale_seconds=120,
            delta="0.22" if short else "-0.22",
            gamma="0.01",
            theta="-0.28" if short else "0.28",
            vega="-2.5" if short else "2.5",
        ),
        _make_leg(
            leg_id=f"{combo_id}-call-long",
            symbol="SPY 20251018C00445000",
            underlying="SPY",
            expiry="2025-10-18",
            dte=45,
            right="CALL",
            strike="445",
            quantity=str(signs[3]),
            avg_cost="0.32",
            mark="0.30",
            mark_source="MID",
            stale_seconds=120,
            delta="-0.14" if short else "0.14",
            gamma="-0.01",
            theta="0.16" if short else "-0.16",
            vega="1.2" if short else "-1.2",
        ),
    )

    combo = _make_combo(
        combo_id=combo_id,
        strategy=ComboStrategy.IRON_CONDOR,
        underlying="SPY",
        dte=45,
        net_price=net_price,
        delta="0.0",
        gamma="0.0",
        theta="0.0",
        vega="0.0",
        legs=legs,
    )
    return combo


def test_long_and_short_vertical_cancel_to_zero() -> None:
    short_vertical = _build_vertical("vertical-credit", "0.70")
    long_vertical = _build_vertical("vertical-debit", "-0.70")

    result = group_option_combos((short_vertical, long_vertical))
    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.group_qty == Decimal("0")


def test_credit_and_debit_condors_sum_signs() -> None:
    combos = (
        _build_condor("condor-short-1", "1.20"),
        _build_condor("condor-short-2", "1.05"),
        _build_condor("condor-short-3", "1.15"),
        _build_condor("condor-long", "-1.10"),
    )

    result = group_option_combos(combos)
    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.group_qty == Decimal("-2")


def test_group_quantity_independent_of_combo_order() -> None:
    combos = (
        _build_vertical("ordered-credit", "0.60"),
        _build_vertical("ordered-debit", "-0.60"),
    )
    forward = group_option_combos(combos)
    reverse = group_option_combos(tuple(reversed(combos)))

    assert forward.groups[0].group_qty == Decimal("0")
    assert reverse.groups[0].group_qty == Decimal("0")
