"""
technicals.py - A library of technical analysis functions.
"""

import pandas as pd


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates a standard set of technical indicators on an OHLCV DataFrame.
    The input DataFrame must have columns: [date, open, high, low, close, volume]
    and be grouped by ticker.
    """
    if df.empty:
        return df

    # Ensure the DataFrame is sorted by date
    df = df.sort_values(["ticker", "date"])
    grp = df.groupby("ticker")

    # Simple Moving Averages
    for period in [20, 50, 200]:
        df[f"sma{period}"] = grp["close"].transform(lambda s: s.rolling(period).mean())

    # Exponential Moving Average
    df["ema20"] = grp["close"].transform(lambda s: s.ewm(span=20, adjust=False).mean())

    # Relative Strength Index (RSI)
    delta = grp["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    df["rsi14"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = grp["close"].transform(lambda s: s.ewm(span=12, adjust=False).mean())
    ema26 = grp["close"].transform(lambda s: s.ewm(span=26, adjust=False).mean())
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df.groupby("ticker")["macd"].transform(
        lambda s: s.ewm(span=9, adjust=False).mean()
    )

    # Average True Range (ATR)
    tr1 = abs(df["high"] - df["low"])
    tr2 = abs(df["high"] - grp["close"].shift())
    tr3 = abs(df["low"] - grp["close"].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr14"] = tr.groupby(df["ticker"]).transform(
        lambda s: s.ewm(alpha=1 / 14, adjust=False).mean()
    )

    # Bollinger Bands
    sma20 = df.groupby("ticker")["close"].transform(lambda s: s.rolling(20).mean())
    std20 = df.groupby("ticker")["close"].transform(lambda s: s.rolling(20).std())
    df["bb_upper"] = sma20 + (std20 * 2)
    df["bb_lower"] = sma20 - (std20 * 2)

    # Realized Volatility
    df["real_vol_30"] = (
        grp["close"].pct_change().transform(lambda s: s.rolling(30).std() * (252**0.5))
    )

    # ADX
    plus_dm = (df["high"].diff()).where(
        (df["high"].diff() > df["low"].diff().abs()) & (df["high"].diff() > 0), 0
    )
    minus_dm = (df["low"].diff()).where(
        (df["low"].diff() > df["high"].diff().abs()) & (df["low"].diff() > 0), 0
    )
    tr14 = tr.rolling(14).sum()
    pdi = 100 * plus_dm.rolling(14).sum() / tr14
    mdi = 100 * minus_dm.rolling(14).sum() / tr14
    df["adx14"] = ((pdi - mdi).abs() / (pdi + mdi) * 100).rolling(14).mean()

    return df
