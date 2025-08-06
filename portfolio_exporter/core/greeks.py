"""Black-Scholes Greek helpers."""

from __future__ import annotations

import math
from typing import Dict, Tuple

from scipy.stats import norm


def _d1_d2(s: float, k: float, t: float, r: float, vol: float) -> Tuple[float, float]:
    """Return the ``d1`` and ``d2`` terms of the Black-Scholes formula."""

    d1 = (math.log(s / k) + (r + 0.5 * vol**2) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    return d1, d2


def bs_greeks(
    s: float,
    k: float,
    t: float,
    r: float,
    vol: float,
    *,
    call: bool = True,
    multiplier: int = 100,
) -> Dict[str, float]:
    """Return Delta, Gamma, Theta and Vega for a vanilla option.

    Values are per contract using ``multiplier`` (typically 100).
    """

    d1, d2 = _d1_d2(s, k, t, r, vol)
    if call:
        delta = norm.cdf(d1)
        theta = -s * norm.pdf(d1) * vol / (2 * math.sqrt(t)) - r * k * math.exp(
            -r * t
        ) * norm.cdf(d2)
    else:
        delta = -norm.cdf(-d1)
        theta = -s * norm.pdf(d1) * vol / (2 * math.sqrt(t)) + r * k * math.exp(
            -r * t
        ) * norm.cdf(-d2)

    gamma = norm.pdf(d1) / (s * vol * math.sqrt(t))
    vega = s * norm.pdf(d1) * math.sqrt(t)
    return {
        "delta": delta * multiplier,
        "gamma": gamma * multiplier,
        "vega": vega * multiplier / 100,  # IB convention: per 1% move
        "theta": theta * multiplier / 365,  # per-day decay
    }
