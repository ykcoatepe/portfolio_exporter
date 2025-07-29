"""
tech_scan.py  –  Ad-hoc technical-indicator exporter for arbitrary tickers.
Usage (internal): run(tickers=["AAPL","SHOP"], fmt="csv")
"""

from typing import Sequence

import pandas as pd
import yfinance as yf

from portfolio_exporter.core import io
from portfolio_exporter.core.config import settings


def _calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["sma_20"] = df["Close"].rolling(20).mean()
    out["rsi_14"] = _rsi(df["Close"], 14)
    out["macd"] = _macd(df["Close"])
    return out


def _rsi(series: pd.Series, n: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(n).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(n).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.Series:
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    return macd


# --------------------------------------------------------------------- #


def run(tickers: Sequence[str], fmt: str = "csv") -> None:
    frames = []
    for t in tickers:
        hist = yf.download(t, period="90d", progress=False)
        if hist.empty:
            continue
        hist = hist.rename_axis("Date").reset_index()
        ind = _calc_indicators(hist)
        ind.insert(0, "Ticker", t)
        frames.append(ind)
    if not frames:
        print("⚠️  No data downloaded.")
        return
    df = pd.concat(frames)
    io.save(df, name="tech_scan", fmt=fmt, outdir=settings.output_dir)
