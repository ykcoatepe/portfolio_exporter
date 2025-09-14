"""Risk band evaluation (v0.1)."""

from __future__ import annotations

from typing import Dict, Tuple


def evaluate(vix: float, delta_beta: float, var95_1d: float, margin_used: float) -> Tuple[str, Dict[str, bool]]:
    """Return band key and breach flags for delta-beta, VaR, and margin.

    Bands per config/rules.yaml v0.1 defaults.
    """
    if vix <= 20:
        band = "vix_le_20"
        beta_min, beta_max = 0.45, 0.60
        var_max, margin_max = 0.009, 0.70
    elif vix <= 30:
        band = "vix_20_30"
        beta_min, beta_max = 0.40, 0.55
        var_max, margin_max = 0.008, 0.60
    else:
        band = "vix_gt_30"
        beta_min, beta_max = 0.35, 0.50
        var_max, margin_max = 0.007, 0.50
    breaches = {
        "beta_low": delta_beta < beta_min,
        "beta_high": delta_beta > beta_max,
        "var_high": var95_1d > var_max,
        "margin_high": margin_used > margin_max,
    }
    return band, breaches
