'''import math
from typing import Dict


def norm_cdf(x: float) -> float:
    """Return cumulative normal distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_delta(S, K, T, r, sigma, call=True):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return norm_cdf(d1) if call else norm_cdf(d1) - 1.0


def bs_greeks(S: float, K: float, T: float, r: float, sigma: float, call: bool = True) -> Dict[str, float]:
    """Closed-form Black–Scholes Greeks per contract."""
    if (
        S <= 0
        or K <= 0
        or T <= 0
        or sigma <= 0
        or any(map(math.isnan, (S, K, T, sigma)))
    ):
        return dict(delta=math.nan, gamma=math.nan, vega=math.nan, theta=math.nan)

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    pdf_d1 = math.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi)

    if call:
        delta = norm_cdf(d1)
        theta = (
            -S * pdf_d1 * sigma / (2 * math.sqrt(T))
            - r * K * math.exp(-r * T) * norm_cdf(d2)
        ) / 365.0
    else:
        delta = norm_cdf(d1) - 1.0
        theta = (
            -S * pdf_d1 * sigma / (2 * math.sqrt(T))
            + r * K * math.exp(-r * T) * norm_cdf(-d2)
        ) / 365.0

    gamma = pdf_d1 / (S * sigma * math.sqrt(T))
    vega = S * pdf_d1 * math.sqrt(T) / 100.0

    return dict(delta=delta, gamma=gamma, vega=vega, theta=theta)
''
