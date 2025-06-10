"""Daily market pulse report."""

from __future__ import annotations

import logging
import os
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

try:
    from ib_insync import IB, Stock, util

    IB_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    IB_AVAILABLE = False

from historic_prices import fetch_and_prepare_data


TICKERS = [
    "ES=F",
    "NQ=F",
    "RTY=F",
    "GDAXI",
    "NKD=F",
    "^VIX",
    "MOVE",
    "^VIX3M",
]

IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7497, 9

LOG_FILE = "daily_pulse.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Save reports to iCloud Drive ▸ Downloads (same as other scripts)
OUTPUT_DIR = (
    "/Users/yordamkocatepe/Library/Mobile Documents/" "com~apple~CloudDocs/Downloads"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ----------------------------------------------------------------------
# Data fetching helpers
# ----------------------------------------------------------------------


def _fetch_ib(tickers: list[str], days: int = 60) -> pd.DataFrame:
    if not IB_AVAILABLE:
        return pd.DataFrame()
    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CID, timeout=3)
    except Exception:
        return pd.DataFrame()
    rows: list[pd.DataFrame] = []
    for tk in tickers:
        try:
            stk = Stock(tk, "SMART", "USD")
            bars = ib.reqHistoricalData(
                stk,
                endDateTime="",
                durationStr=f"{days} D",
                barSizeSetting="1 day",
                whatToShow="MIDPOINT",
                useRTH=True,
            )
            if bars:
                df = util.df(bars)
                df["Ticker"] = tk
                rows.append(df)
        except Exception:
            continue
    ib.disconnect()
    if not rows:
        return pd.DataFrame()
    df_all = pd.concat(rows, ignore_index=True)
    df_all = df_all.rename(
        columns={
            "date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "Ticker": "ticker",
        }
    )
    df_all["adj_close"] = df_all["close"]
    return df_all[
        ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]
    ]


def fetch_prices(tickers: list[str]) -> pd.DataFrame:
    df = _fetch_ib(tickers)
    if df.empty:
        df = fetch_and_prepare_data(tickers)
    return df


# ----------------------------------------------------------------------
# Indicator calculations
# ----------------------------------------------------------------------


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    results = []
    df = df.sort_values(["ticker", "date"])
    for ticker, sub in df.groupby("ticker"):
        sub = sub.copy()
        sub["sma20"] = sub["close"].rolling(20).mean()
        sub["ema20"] = sub["close"].ewm(span=20, adjust=False).mean()
        # ATR
        hl = sub["high"] - sub["low"]
        hcp = (sub["high"] - sub["close"].shift()).abs()
        lcp = (sub["low"] - sub["close"].shift()).abs()
        tr = pd.concat([hl, hcp, lcp], axis=1).max(axis=1)
        sub["atr14"] = tr.rolling(14).mean()
        sub["rsi14"] = _rsi(sub["close"], 14)
        ema12 = sub["close"].ewm(span=12, adjust=False).mean()
        ema26 = sub["close"].ewm(span=26, adjust=False).mean()
        sub["macd"] = ema12 - ema26
        sub["macd_signal"] = sub["macd"].ewm(span=9, adjust=False).mean()
        mavg = sub["close"].rolling(20).mean()
        mstd = sub["close"].rolling(20).std()
        sub["bb_upper"] = mavg + 2 * mstd
        sub["bb_lower"] = mavg - 2 * mstd
        tp = (sub["high"] + sub["low"] + sub["close"]) / 3
        sub["vwap"] = (tp * sub["volume"]).cumsum() / sub["volume"].cumsum()
        sub["pct_change"] = sub["close"].pct_change() * 100
        sub["real_vol_30"] = sub["close"].pct_change().rolling(30).std() * np.sqrt(252)
        results.append(sub)
    return pd.concat(results, ignore_index=True)


# ----------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------


def generate_report(df: pd.DataFrame, output_path: str) -> None:
    """Write latest ticker metrics to ``output_path`` as CSV."""
    latest = df.sort_values("date").groupby("ticker").tail(1)
    table = latest[
        [
            "ticker",
            "close",
            "pct_change",
            "rsi14",
            "atr14",
        ]
    ].sort_values("ticker")
    table.to_csv(output_path, index=False)


# ----------------------------------------------------------------------
# main entry
# ----------------------------------------------------------------------


def main() -> None:
    out_name = datetime.utcnow().strftime("daily_pulse_%Y%m%d_%H%M.cvs")
    out_path = os.path.join(OUTPUT_DIR, out_name)
    try:
        data = fetch_prices(TICKERS)
        if data.empty:
            logger.error("No data fetched.")
            return
        data = compute_indicators(data)
        generate_report(data, out_path)
        logger.info("Report written to %s", out_path)
    except Exception as e:  # pragma: no cover - entry point
        logger.exception("daily_pulse failed: %s", e)


if __name__ == "__main__":  # pragma: no cover - script entry
    main()
