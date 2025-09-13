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

    # Avoid division by zero
    rs = gain / loss
    rs.replace([float('inf'), -float('inf')], float('nan'), inplace=True)
    rs.fillna(0, inplace=True)

    rsi = 100 - (100 / (1 + rs))
    return rsi


def _macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.Series:
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    return macd


# --------------------------------------------------------------------- #


def run(tickers: Sequence[str], fmt: str = "csv") -> None:
    # Normalize and de-duplicate user input
    symbols = []
    seen = set()
    for t in tickers:
        norm = (t or "").strip().upper()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        symbols.append(norm)

    frames = []
    for t in symbols:
        try:
            hist = yf.download(t, period="90d", progress=False)
        except Exception as exc:  # network or symbol errors
            print(f"⚠️  Download failed for {t}: {exc}")
            continue
        if hist is None or getattr(hist, "empty", True):
            print(f"⚠️  No data for {t}")
            continue
        hist = hist.rename_axis("Date").reset_index()
        if "Close" not in hist.columns:
            print(f"⚠️  Unexpected columns for {t}; skipping")
            continue
        ind = _calc_indicators(hist)
        ind.insert(0, "Ticker", t)
        frames.append(ind)
    if not frames:
        print("⚠️  No data downloaded.")
        return
    df = pd.concat(frames, ignore_index=True)
    io.save(df, name="tech_scan", fmt=fmt, outdir=settings.output_dir)
