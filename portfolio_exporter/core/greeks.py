"""Black-Scholes Greek helpers."""

from __future__ import annotations

import math

try:  # optional SciPy; provide lightweight fallbacks
    from scipy.stats import norm  # type: ignore

    _cdf = norm.cdf
    _pdf = norm.pdf
except Exception:
    # Abramowitz-Stegun approximation for erf → normal CDF
    def _erf(x: float) -> float:
        # Numerical approximation of error function
        # Source: Numerical Recipes / Abramowitz-Stegun
        t = 1.0 / (1.0 + 0.5 * abs(x))
        tau = t * math.exp(
            -x * x
            - 1.26551223
            + 1.00002368 * t
            + 0.37409196 * t**2
            + 0.09678418 * t**3
            - 0.18628806 * t**4
            + 0.27886807 * t**5
            - 1.13520398 * t**6
            + 1.48851587 * t**7
            - 0.82215223 * t**8
            + 0.17087277 * t**9
        )
        return 1 - tau if x >= 0 else tau - 1

    def _cdf(x: float) -> float:
        return 0.5 * (1.0 + _erf(x / math.sqrt(2.0)))

    def _pdf(x: float) -> float:
        return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)


def _d1_d2(s: float, k: float, t: float, r: float, vol: float) -> tuple[float, float]:
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
) -> dict[str, float]:
    """Return Delta, Gamma, Theta and Vega for a vanilla option.

    Values are per contract using ``multiplier`` (typically 100).
    """

    d1, d2 = _d1_d2(s, k, t, r, vol)
    if call:
        delta = _cdf(d1)
        theta = -s * _pdf(d1) * vol / (2 * math.sqrt(t)) - r * k * math.exp(-r * t) * _cdf(d2)
    else:
        delta = -_cdf(-d1)
        theta = -s * _pdf(d1) * vol / (2 * math.sqrt(t)) + r * k * math.exp(-r * t) * _cdf(-d2)

    gamma = _pdf(d1) / (s * vol * math.sqrt(t))
    vega = s * _pdf(d1) * math.sqrt(t)
    return {
        "delta": delta * multiplier,
        "gamma": gamma * multiplier,
        "vega": vega * multiplier / 100,  # IB convention: per 1% move
        "theta": theta * multiplier / 365,  # per-day decay
    }
