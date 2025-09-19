"""VaR analytics (v0.1)."""

from __future__ import annotations

import math
from collections.abc import Sequence


def var95_1d_from_closes(closes: Sequence[float], nav_exposed: float) -> float:
    """Historical 1d VaR at 95% given recent closes and exposed NAV.

    Returns a non-negative float representing absolute VaR (currency units).
    Parametric fallback is used if not enough history is available.
    """
    xs = [float(x) for x in closes if isinstance(x, (int, float)) and math.isfinite(float(x))]
    if len(xs) < 2:
        return 0.0
    rets = []
    for i in range(1, len(xs)):
        try:
            r = (xs[i] - xs[i - 1]) / xs[i - 1]
            if math.isfinite(r):
                rets.append(r)
        except Exception:
            continue
    if not rets:
        return 0.0
    if len(rets) < 2:
        # Minimal fallback when only one return is available
        return abs(rets[0]) * float(nav_exposed)
    rets_sorted = sorted(rets)
    if len(rets_sorted) >= 252:
        idx = max(0, int(0.05 * len(rets_sorted)) - 1)
        q = rets_sorted[idx]
        return abs(q) * float(nav_exposed)
    # parametric fallback – z(95%) one-sided ~ 1.645, use 22-day sigma proxy
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(1, (len(rets) - 1))
    sigma = math.sqrt(var)
    z = 1.645
    return z * sigma * float(nav_exposed)
