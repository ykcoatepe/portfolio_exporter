from __future__ import annotations

import logging
import math
import time
from typing import List, Tuple

import pandas as pd
import numpy as np

try:
    from ib_insync import IB, Position, Ticker
except Exception:  # pragma: no cover - optional
    IB = Position = Ticker = None  # type: ignore


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


TIMEOUT_SECONDS = 40


def _has_any_greeks_populated(ticker: Ticker) -> bool:
    for name in ("modelGreeks", "lastGreeks", "bidGreeks", "askGreeks"):
        g = getattr(ticker, name, None)
        if g and g.delta is not None and not math.isnan(g.delta):
            return True
    return False


def list_positions(ib: IB) -> List[Tuple[Position, Ticker]]:
    """Retrieve option/FOP positions and live market data streams for Greeks."""
    if IB is None:
        try:
            from ib_insync import IB as _IB, Position as _Pos, Ticker as _Ticker
        except Exception:
            return []
        else:
            globals()["IB"] = _IB
            globals()["Position"] = _Pos
            globals()["Ticker"] = _Ticker
    positions = [
        p
        for p in ib.portfolio()
        if p.position != 0 and p.contract.secType in {"OPT", "FOP"}
    ]
    if not positions:
        return []

    bundles: List[Tuple[Position, Ticker]] = []
    for pos in positions:
        qc = ib.qualifyContracts(pos.contract)
        if not qc:
            continue
        c = qc[0]
        if not c.exchange:
            c.exchange = "SMART"
        tk = ib.reqMktData(
            c, genericTickList="106", snapshot=False, regulatorySnapshot=False
        )
        bundles.append((pos, tk))

    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        ib.sleep(0.25)
        if all(_has_any_greeks_populated(tk) for _, tk in bundles):
            break
    return bundles
