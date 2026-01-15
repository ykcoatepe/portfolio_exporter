# SPDX-License-Identifier: MIT

"""Verification tests for PlaybookMetrics logic."""

from datetime import UTC, datetime, timedelta

from positions_engine.service.playbook_metrics import (
    PlaybookMetrics,
    _compute_v_vix_cap,
    evaluate_hysteresis,
    reset_hysteresis,
)


def test_v_vix_cap_logic():
    """Verify cap scaling and penalties per Playbook v4."""
    # VIX 15-20 -> 1000 base. NAV 1M -> cap 1000.
    assert _compute_v_vix_cap(16.0, 1_000_000, False, 15.0) == 1000.0

    # Backwardation penalty (VX1 > VX2) -> -20% -> 800
    assert _compute_v_vix_cap(16.0, 1_000_000, True, 15.0) == 800.0

    # VVIX penalty (>= 110) -> -10% -> 900
    assert _compute_v_vix_cap(16.0, 1_000_000, False, 115.0) == 900.0

    # Both -> 1000 * 0.8 * 0.9 = 720
    assert _compute_v_vix_cap(16.0, 1_000_000, True, 115.0) == 720.0

    # VIX >= 30 -> 300 base
    assert _compute_v_vix_cap(35.0, 1_000_000, False, 15.0) == 300.0


def test_hysteresis_state_machine():
    """Verify 3-session guard on risk state transitions."""
    reset_hysteresis("ON")
    start = datetime(2026, 1, 2, tzinfo=UTC)

    # 1. Steady state ON
    assert evaluate_hysteresis(15, False, 0.0, as_of=start) == "ON"

    # 2. Trigger OFF condition (VIX > 30). Should be protected by hysteresis.
    # Logic: ON -> NEUTRAL (VIX > 20) -> OFF (VIX > 30)
    # VIX 31 triggers "ON -> NEUTRAL" logic first?
    # _evaluate_risk_transition(ON, 31...) -> NEUTRAL.

    # Session 1: Signal NEUTRAL
    assert evaluate_hysteresis(31, False, 0.0, as_of=start + timedelta(days=1)) == "ON"
    # Session 2: Signal NEUTRAL
    assert evaluate_hysteresis(31, False, 0.0, as_of=start + timedelta(days=2)) == "ON"
    # Session 3: Transition to NEUTRAL
    assert (
        evaluate_hysteresis(31, False, 0.0, as_of=start + timedelta(days=3))
        == "NEUTRAL"
    )

    # Now in NEUTRAL. VIX 31 triggers NEUTRAL -> OFF immediately?
    # _evaluate_risk_transition(NEUTRAL, 31...) -> OFF.
    # Hysteresis applies again.

    # Session 1 (in Neutral): Signal OFF
    assert (
        evaluate_hysteresis(31, False, 0.0, as_of=start + timedelta(days=4))
        == "NEUTRAL"
    )
    # Session 2
    assert (
        evaluate_hysteresis(31, False, 0.0, as_of=start + timedelta(days=5))
        == "NEUTRAL"
    )
    # Session 3 -> Transition to OFF
    assert evaluate_hysteresis(31, False, 0.0, as_of=start + timedelta(days=6)) == "OFF"


def test_metrics_from_powerlaw():
    """Verify metrics extraction from powerlaw dict."""
    reset_hysteresis("ON")
    pl = {"signals": {"vix": 18.0, "vvix": 95.0, "vx1": 18.0, "vx2": 19.0}}

    # Normal case
    m = PlaybookMetrics.from_powerlaw(pl, net_vega=-1000, nav_ref=1_000_000)
    assert m.vix == 18.0
    assert m.v_vix_ratio == 1000 / 18.0  # ~55.5
    assert m.risk_state == "ON"
    assert m.vix_available is True

    # Missing data case
    m_empty = PlaybookMetrics.from_powerlaw(None)
    assert m_empty.vix_available is False
    assert m_empty.risk_state == "ON"  # Default
