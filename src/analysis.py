from __future__ import annotations

import logging
import math
import time
from typing import List, Tuple

import pandas as pd
from rich.console import Console

console = Console(stderr=True)
import numpy as np

try:
    from ib_insync import IB, Position, Ticker
except Exception:  # pragma: no cover - optional
    IB = Position = Ticker = None  # type: ignore

TIMEOUT_SECONDS = 40


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute common technical indicators for a price dataframe."""
    df = df.sort_values(["ticker", "date"]).copy()
    grp = df.groupby("ticker", group_keys=False)

    df["pct_change"] = grp["close"].pct_change(fill_method=None)
    df["sma20"] = grp["close"].transform(lambda s: s.rolling(20).mean())
    df["ema20"] = grp["close"].transform(lambda s: s.ewm(span=20).mean())

    delta = grp["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["rsi14"] = 100 - 100 / (1 + rs)

    ema12 = grp["close"].transform(lambda s: s.ewm(span=12).mean())
    ema26 = grp["close"].transform(lambda s: s.ewm(span=26).mean())
    df["macd"] = ema12 - ema26
    df["macd_signal"] = grp["macd"].transform(lambda s: s.ewm(span=9).mean())

    tr = (
        (df["high"] - df["low"])
        .abs()
        .to_frame("hl")
        .join((df["high"] - grp["close"].shift()).abs().to_frame("hc"))
        .join((df["low"] - grp["close"].shift()).abs().to_frame("lc"))
        .max(axis=1)
    )
    df["atr14"] = (
        tr.groupby(df["ticker"], group_keys=False)
        .rolling(14)
        .mean()
        .reset_index(level=0, drop=True)
    )

    m20 = df["sma20"]
    std20 = grp["close"].transform(lambda s: s.rolling(20).std())
    df["bb_upper"] = m20 + 2 * std20
    df["bb_lower"] = m20 - 2 * std20

    df["vwap"] = (df["close"] * df["volume"]).groupby(df["ticker"]).cumsum() / df[
        "volume"
    ].groupby(df["ticker"]).cumsum()
    df["real_vol_30"] = grp["pct_change"].transform(
        lambda s: s.rolling(30).std() * (252**0.5)
    )
    return df


def eddr(
    path: pd.Series, horizon_days: int = 252, alpha: float = 0.99
) -> Tuple[float, float]:
    """Extreme Downside Draw-down Risk."""
    window_dd = (
        path.rolling(window=horizon_days, min_periods=horizon_days)
        .apply(lambda w: ((w.cummax() - w) / w.cummax()).max(), raw=False)
        .dropna()
    )
    if window_dd.empty:
        return math.nan, math.nan

    dar_val = float(np.quantile(window_dd, alpha))
    cdar_val = float(window_dd[window_dd >= dar_val].mean())
    return dar_val, cdar_val


def list_positions(ib: IB):
    """Proxy to :func:`src.data_fetching.list_positions`."""
    from .data_fetching import list_positions as _lp

    return _lp(ib)


def calc_portfolio_greeks(
    positions: pd.DataFrame,
    holdings: pd.DataFrame | None = None,
    include_indices: bool = False,
) -> pd.DataFrame:
    """Aggregate Greek exposures by underlying and for the full portfolio.

    Optionally filter out index underlyings unless include_indices is True or the index
    is present in the holdings DataFrame.
    """
    if positions.empty:
        return pd.DataFrame()

    # filter index underlyings if not explicitly included
    if not include_indices:
        index_names = {"VIX", "^VIX", "SPX", "^SPX", ""}
        if holdings is not None:
            # determine which underlyings are truly held
            if "underlying" in holdings.columns:
                held = set(holdings["underlying"].astype(str))
            elif "symbol" in holdings.columns:
                held = set(holdings["symbol"].astype(str))
            else:
                held = set()
        else:
            held = set()
        # identify and warn about skipped index tickers
        to_drop = positions.loc[
            positions["underlying"].isin(index_names)
            & ~positions["underlying"].isin(held),
            "underlying",
        ].unique()
        for sym in to_drop:
            console.print(f"[yellow]Skipped index ticker: {sym}[/]")
        # drop rows for index names not in held
        positions = positions.loc[
            ~(
                positions["underlying"].isin(index_names)
                & ~positions["underlying"].isin(held)
            )
        ]

    cols = ["delta", "gamma", "vega", "theta", "rho"]
    df = positions.copy()
    for c in cols + ["position", "multiplier"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        else:
            df[c] = 0.0
    df["multiplier"] = df["multiplier"].replace(0, 1)
    weight = df["position"] * df["multiplier"]
    exposures = df[cols].to_numpy() * weight.to_numpy()[:, None]
    out = pd.DataFrame(exposures, columns=cols)
    out["underlying"] = (
        df["underlying"] if "underlying" in df.columns else df.get("symbol")
    )
    agg = out.groupby("underlying")[cols].sum()
    total = agg.sum().to_frame().T
    total.index = ["PORTFOLIO_TOTAL"]
    return pd.concat([agg, total])
