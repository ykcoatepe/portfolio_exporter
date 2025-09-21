"""Validate mark source aggregation prefers MID over LAST over PREV for combo legs."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from itertools import permutations

import pytest
from positions_engine.combos import (
    ComboStrategy,
    OptionCombo,
    OptionLegSnapshot,
    group_option_combos,
)


def _make_leg(
    *,
    leg_id: str,
    mark_source: str,
    stale_seconds: int | None,
    right: str = "CALL",
) -> OptionLegSnapshot:
    return OptionLegSnapshot(
        leg_id=leg_id,
        instrument_symbol=f"SYM-{leg_id}",
        account="acct-1",
        underlying="SPY",
        expiry="2025-01-17",
        dte=30,
        right=right,
        strike=Decimal("400"),
        quantity=Decimal("1"),
        ratio=Decimal("1"),
        multiplier=Decimal("100"),
        avg_cost=Decimal("1.00"),
        mark=Decimal("1.00"),
        mark_source=mark_source,
        stale_seconds=stale_seconds,
        previous_close=None,
        delta=Decimal("0"),
        gamma=Decimal("0"),
        theta=Decimal("0"),
        vega=Decimal("0"),
        iv=None,
        day_pnl=Decimal("0"),
        total_pnl=Decimal("0"),
        day_basis=None,
        total_basis=None,
    )


def _aggregate_mark_source(
    mark_sources: Sequence[str],
    stale_values: Sequence[int | None] | None = None,
) -> tuple[str, int | None]:
    legs = []
    for index, source in enumerate(mark_sources):
        stale = None if stale_values is None else stale_values[index]
        right = "CALL" if index % 2 == 0 else "PUT"
        legs.append(
            _make_leg(
                leg_id=f"leg-{index}",
                mark_source=source,
                stale_seconds=stale,
                right=right,
            )
        )

    combo = OptionCombo(
        combo_id="combo-1",
        strategy=ComboStrategy.VERTICAL,
        account="acct-1",
        underlying="SPY",
        dte=30,
        net_price=Decimal("0"),
        sum_delta=Decimal("0"),
        sum_gamma=Decimal("0"),
        sum_theta=Decimal("0"),
        sum_vega=Decimal("0"),
        day_pnl=Decimal("0"),
        total_pnl=Decimal("0"),
        day_pnl_percent=None,
        total_pnl_percent=None,
        legs=tuple(legs),
    )

    result = group_option_combos((combo,))
    group = result.groups[0]
    return group.mark_source, group.stale_seconds


@pytest.mark.parametrize(
    ("mark_sources", "expected"),
    [
        ("MID PREV".split(), "MID"),
        ("MID LAST".split(), "MID"),
        ("LAST PREV".split(), "LAST"),
        ("PREV PREV PREV".split(), "PREV"),
    ],
)
def test_best_mark_source_selected(mark_sources: Sequence[str], expected: str) -> None:
    """NBBO midpoint approximates fair value; the last trade is a single print subject to noise and latency; previous close is only a baseline, so MID ≻ LAST ≻ PREV."""

    mark_source, _ = _aggregate_mark_source(mark_sources)
    assert mark_source == expected


def test_mark_source_is_case_insensitive() -> None:
    mark_source, _ = _aggregate_mark_source(["mid", "preV"])
    assert mark_source == "MID"


def test_mark_source_trims_whitespace() -> None:
    mark_source, _ = _aggregate_mark_source([" MISSING ", " mid "])
    assert mark_source == "MID"


def test_staleness_is_conservative() -> None:
    mark_sources = "MID LAST PREV".split()
    stale_values = [12, 95, 7]

    _, stale_seconds = _aggregate_mark_source(mark_sources, stale_values)

    assert stale_seconds == 95


def test_mark_source_reduction_is_idempotent() -> None:
    entries = "MID LAST PREV".split()
    baseline = tuple(entries)

    round_trip = {
        perm: _aggregate_mark_source(list(perm))[0]
        for perm in permutations(entries)
    }

    assert len(set(round_trip.values())) == 1
    assert round_trip[baseline] == "MID"
