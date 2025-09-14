from __future__ import annotations

from src.psd.ui.cli import render_dashboard


def test_cli_rollup_snapshot():
    dto = {
        "snapshot": {
            "vix": 22.0,
            "delta_beta": 0.52,
            "var95_1d": 800.0,
            "band": "vix_20_30",
            "breaches": {"beta_high": True, "var_high": False, "margin_high": False},
            "breakers": {"soft_pre": False},
            "margin_used": 0.42,
        },
        "rows": [
            {"uid": "SPY-20260117-iron_condor", "sleeve": "theta", "kind": "iron_condor", "R": 320.0, "stop": "-", "target": "-", "mark": 1.6, "alert": "tp"}
        ],
    }
    out = render_dashboard(dto)
    assert "Regime: 15-25" in out
    assert "BREACH:" in out
    assert "SPY-20260117-iron_condor" in out

