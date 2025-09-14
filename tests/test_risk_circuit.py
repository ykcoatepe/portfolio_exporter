from __future__ import annotations

from src.psd.rules.risk_bands import evaluate as eval_band
from src.psd.rules.circuit_breakers import evaluate as eval_cb


def test_risk_bands_and_breakers():
    band, breaches = eval_band(vix=18.0, delta_beta=0.65, var95_1d=0.010, margin_used=0.75)
    assert band == "vix_le_20"
    assert breaches["beta_high"] is True
    assert breaches["var_high"] is True
    assert breaches["margin_high"] is True

    cb = eval_cb(daily_return=-0.02, var_change=-0.001)
    assert cb["soft_pre"] is True
    assert cb["freeze_1d"] is True
    assert cb["cut_var"] is True

