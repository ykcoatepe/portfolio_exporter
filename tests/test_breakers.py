from __future__ import annotations

from src.psd.rules.circuit_breakers import derive_state, produce_actions


def test_breaker_states_and_actions():
    s1 = derive_state(day_pl=-0.016, month_pl=0.0)
    assert s1["state"] == "freeze_1d"
    s2 = derive_state(day_pl=-0.026, month_pl=0.0)
    assert s2["state"] == "cut_var"
    actions = produce_actions({"by_symbol_var": [{"symbol": "A", "var": 10}, {"symbol": "B", "var": 5}, {"symbol": "C", "var": 1}]})
    assert "A" in actions

