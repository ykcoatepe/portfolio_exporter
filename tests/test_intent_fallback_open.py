import pandas as pd
from portfolio_exporter.scripts.trades_report import _annotate_combos_effect


def test_combo_intent_open_without_prior_snapshot():
    # Minimal combos df with a single leg id
    combos = pd.DataFrame({
        "underlying": ["SPY"],
        "expiry": ["2025-01-01"],
        "structure": ["vertical"],
        "type": ["vertical"],
        "legs": ["[123]"]
    })
    # pos_like providing leg attributes for the id
    pos_like = pd.DataFrame({
        "conId": [123],
        "underlying": ["SPY"],
        "expiry": ["2025-01-01"],
        "right": ["C"],
        "strike": [100.0],
        "qty": [1],
    })
    out = _annotate_combos_effect(combos, pos_like, prev_positions=None)
    assert out.get("position_effect").iloc[0] == "Open"

