from __future__ import annotations

import os
from typing import Any


def _env_float(key: str, default: float) -> float:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def evaluate(risk: dict[str, Any] | None) -> list[str]:
    """Return human-readable breach codes derived from the ``risk`` payload."""
    if not isinstance(risk, dict):
        risk = {}

    beta_min = _env_float("PSD_RULE_BETA_MIN", 0.10)
    var_max = _env_float("PSD_RULE_VAR95_1D_MAX", 0.03)
    margin_max = _env_float("PSD_RULE_MARGIN_MAX", 0.35)

    breaches: list[str] = []
    beta = float(risk.get("beta", risk.get("delta_beta", 0.0)) or 0.0)
    if abs(beta) < beta_min:
        breaches.append("beta_low")

    var_1d = float(risk.get("var95_1d", risk.get("VaR95_1d", 0.0)) or 0.0)
    notional = float(risk.get("notional", risk.get("net_liq", 0.0)) or 0.0)
    if notional:
        var_ratio = var_1d / max(notional, 1.0)
    else:
        var_ratio = var_1d
    if var_ratio > var_max:
        breaches.append("var_spike")

    margin = float(risk.get("margin_pct", risk.get("margin_used", 0.0)) or 0.0)
    if margin > margin_max:
        breaches.append("margin_high")

    return breaches
