import pandas as pd
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
