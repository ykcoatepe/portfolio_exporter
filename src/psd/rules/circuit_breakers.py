"""Circuit breaker evaluation (v0.1)."""

from __future__ import annotations

from typing import Dict


def evaluate(daily_return: float, var_change: float) -> Dict[str, bool]:
    """Return breaker states using v0.1 defaults.

    - soft_pre at -1.0%
    - freeze_1d at -1.5%
    - cut_var at -2.5% or worsening VaR change
    """
    soft_pre = daily_return <= -0.010
    freeze_1d = daily_return <= -0.015
    cut_var = daily_return <= -0.025 or var_change < 0
    return {"soft_pre": soft_pre, "freeze_1d": freeze_1d, "cut_var": cut_var}
