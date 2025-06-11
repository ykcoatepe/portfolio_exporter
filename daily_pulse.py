import os
import argparse
from datetime import datetime

import pandas as pd
import numpy as np

DATE_TAG = datetime.utcnow().strftime("%Y%m%d")
TIME_TAG = datetime.utcnow().strftime("%H%M")
OUTPUT_DIR = (
    "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)
DEFAULT_OUTPUT = os.path.join(OUTPUT_DIR, f"daily_pulse_{DATE_TAG}_{TIME_TAG}.csv")


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return DataFrame with technical indicators."""
    df = df.sort_values("date").copy()
    grp = df.groupby("ticker")
    df["pct_change"] = grp["close"].pct_change(fill_method=None)
    df["sma20"] = grp["close"].transform(lambda s: s.rolling(20, min_periods=1).mean())
    df["ema20"] = grp["close"].transform(lambda s: s.ewm(span=20, min_periods=1).mean())
    high_low = df["high"] - df["low"]
    prev_close = grp["close"].shift(1)
    tr = pd.concat(
        [
            high_low,
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["tr"] = tr
    df["atr14"] = grp["tr"].transform(lambda s: s.rolling(14, min_periods=1).mean())
    df.drop(columns="tr", inplace=True)
    delta = grp["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14, min_periods=1).mean()
    avg_loss = loss.rolling(14, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi14"] = 100 - (100 / (1 + rs))
    ema12 = grp["close"].transform(lambda s: s.ewm(span=12, min_periods=1).mean())
    ema26 = grp["close"].transform(lambda s: s.ewm(span=26, min_periods=1).mean())
    df["macd"] = ema12 - ema26
    df["macd_signal"] = grp["macd"].transform(
        lambda s: s.ewm(span=9, min_periods=1).mean()
    )
    rolling_mean = grp["close"].transform(lambda s: s.rolling(20, min_periods=1).mean())
    rolling_std = grp["close"].transform(lambda s: s.rolling(20, min_periods=1).std())
    df["bb_upper"] = rolling_mean + 2 * rolling_std
    df["bb_lower"] = rolling_mean - 2 * rolling_std
    df["vwap"] = grp.apply(
        lambda g: (g["close"] * g["volume"]).cumsum() / g["volume"].cumsum()
    ).reset_index(level=0, drop=True)
    df["real_vol_30"] = grp["pct_change"].transform(
        lambda s: s.rolling(30, min_periods=1).std() * np.sqrt(252)
    )
    return df


def generate_report(df: pd.DataFrame, output_path: str) -> None:
    """
    Write latest metrics for each ticker to ``output_path`` as CSV.

    The report now includes all key technical fields so downstream
    scanners don't miss any derived signals.
    """
    latest = (
        df.sort_values("date")
        .groupby("ticker", as_index=False)
        .tail(1)
        .set_index("ticker", drop=True)
    )

    cols = [
        "close",
        "pct_change",
        "sma20",
        "ema20",
        "atr14",
        "rsi14",
        "macd",
        "macd_signal",
        "bb_upper",
        "bb_lower",
        "vwap",
        "real_vol_30",
    ]

    # keep only existing cols to prevent key errors
    cols = [c for c in cols if c in latest.columns]

    latest = latest[cols].round(4)
    latest.to_csv(output_path)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Generate daily technical summary from OHLC data"
    )
    p.add_argument(
        "csv",
        nargs="?",
        default="historic_prices_sample.csv",
        help="Input OHLCV CSV file",
    )
    p.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT,
        help="Path to save the summary CSV",
    )
    args = p.parse_args()

    df = pd.read_csv(args.csv, parse_dates=["date"])
    df = compute_indicators(df)
    generate_report(df, args.output)
    print(f"✅  Saved report → {args.output}")


if __name__ == "__main__":
    main()
