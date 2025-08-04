from __future__ import annotations

import itertools
from typing import List

import pandas as pd

from .ib import quote_option, quote_stock


def fetch_chain(
    symbol: str, expiry: str, strikes: List[float] | None = None
) -> pd.DataFrame:
    """Return an option chain snapshot.

    The resulting DataFrame includes columns: ``strike``, ``right``, ``mid``,
    ``bid``, ``ask``, ``delta``, ``gamma``, ``vega``, ``theta`` and ``iv``.
    """
    if not strikes:
        spot = quote_stock(symbol)["mid"]
        strikes = [round((spot // 5 + i) * 5, 0) for i in range(-5, 6)]
    rows = []
    for strike, right in itertools.product(strikes, ["C", "P"]):
        try:
            q = quote_option(symbol, expiry, strike, right)
            q.update({"strike": strike, "right": right})
            rows.append(q)
        except ValueError:
            # strike not offered for this weekly; skip gracefully
            continue
    return pd.DataFrame(rows)
