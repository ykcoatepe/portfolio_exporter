#!/usr/bin/env python3
"""
tech_signals.py  —  Live technical indicator dump for TRADER playbook
---------------------------------------------------------------------
Outputs: tech_signals.csv
Columns: timestamp · ticker · ADX · ATR · 20dma · 50dma · 200dma · IV_rank · RSI · beta_SPY
Run pre-open, mid-session, or whenever you want fresh scans.
"""

import os, sys, pandas as pd, numpy as np, yfinance as yf
from datetime import datetime
import time, logging

# ───────────────────────── CONFIG ──────────────────────────
PORTFOLIO_FILES = ["tickers_live.txt", "tickers.txt"]  # first existing wins
OUTPUT_CSV      = "tech_signals.csv"
HIST_DAYS       = 300                                   # enough for SMA200 & ADX
REF_INDEX       = "SPY"                                 # benchmark for beta

# ─────────────────────── LOGGING ────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Directory where we persist per‑ticker IV history for IV Rank calc
DATA_DIR = "iv_history"
os.makedirs(DATA_DIR, exist_ok=True)

# Friendly tag → valid ticker mapping
PROXY_MAP = {
    "VIX":  "^VIX",
    "VVIX": "^VVIX",
    "DXY":  "DX-Y.NYB"
}

# ────────────────────── HELPER FUNCTIONS ───────────────────
def load_tickers() -> list[str]:
    """Return tickers listed in the first existing portfolio file."""
    path = next((p for p in PORTFOLIO_FILES if os.path.exists(p)), None)
    if not path:
        sys.stderr.write("❗ No portfolio ticker file found; aborting tech scan.\n")
        return []
    with open(path) as f:
        raw = [ln.strip().upper() for ln in f if ln.strip()]
    return [PROXY_MAP.get(t, t) for t in raw]

def fetch_history(ticker: str, days: int = HIST_DAYS) -> pd.DataFrame:
    """
    Robust daily-bar fetch:
      1) Try fast bulk yf.download
      2) If missing OHLC columns or empty, retry via slower .history()
    Returns clean DataFrame or empty if unavailable.
    """
    # --- Fast path ----------------------------------------------------
    try:
        df = yf.download(
            ticker,
            period=f"{days}d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            group_by="column",         # avoid MultiIndex for single ticker
        )
    except Exception:
        df = pd.DataFrame()

    need_cols = {"Open", "High", "Low", "Close"}

    # --- Fallback path ------------------------------------------------
    if df.empty or need_cols.difference(df.columns):
        try:
            df = yf.Ticker(ticker).history(
                period=f"{days}d",
                interval="1d",
                auto_adjust=False,
            )
        except Exception as e:
            sys.stderr.write(f"⚠️  {ticker} history fail: {e}\n")
            return pd.DataFrame()

    if need_cols.difference(df.columns):
        sys.stderr.write(f"⚠️  {ticker} missing OHLC columns—skipped\n")
        return pd.DataFrame()

    df.dropna(subset=list(need_cols), inplace=True)
    return df

# Pre-cache SPY returns for beta calculation
_spy_df = fetch_history(REF_INDEX)
if _spy_df.empty or "Close" not in _spy_df.columns:
    _SPY_RET = pd.Series(dtype=float)
else:
    _SPY_RET = _spy_df["Close"].pct_change().dropna()

def calc_indicators(df: pd.DataFrame) -> tuple:
    """Return (ADX14, ATR14, SMA20, SMA50, SMA200, RSI14)."""
    if df.empty:
        return (np.nan, np.nan, np.nan, np.nan, np.nan, np.nan)
    close, high, low = df["Close"], df["High"], df["Low"]

    # Simple moving averages
    sma20  = close.rolling(20).mean().iloc[-1]
    sma50  = close.rolling(50).mean().iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1]

    # RSI-14
    delta = close.diff()
    up   = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs   = up.rolling(14).mean() / down.rolling(14).mean()
    rsi  = 100 - (100 / (1 + rs)).iloc[-1]

    # True Range & ATR-14
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]

    # ADX-14
    plus_dm  = (high.diff()).where((high.diff() > low.diff().abs()) & (high.diff() > 0), 0.0)
    minus_dm = (low.diff()).where((low.diff() > high.diff().abs()) & (low.diff() > 0), 0.0)
    tr14 = tr.rolling(14).sum()
    pdi = 100 * plus_dm.rolling(14).sum() / tr14
    mdi = 100 * minus_dm.rolling(14).sum() / tr14
    adx = ((pdi - mdi).abs() / (pdi + mdi) * 100).rolling(14).mean().iloc[-1]

    return adx, atr, sma20, sma50, sma200, rsi

def current_iv(tkr):
    """ATM implied vol from nearest‑expiry call; NaN on failure."""
    try:
        tk = yf.Ticker(tkr)
        expiries = sorted(tk.options)
        if not expiries:
            return np.nan
        exp = expiries[0]                       # closest expiry
        chain = tk.option_chain(exp).calls
        if chain.empty:
            return np.nan
        spot = tk.history(period="1d")["Close"].iloc[-1]
        atm_row = chain.iloc[(chain["strike"] - spot).abs().argmin()]
        return atm_row["impliedVolatility"]
    except Exception as e:
        logging.warning("IV fetch fail for %s: %s", tkr, e)
        return np.nan

def iv_rank(tkr, iv_now, lookback=252):
    """Update history CSV and return IV Rank in % [0‑100]."""
    if np.isnan(iv_now):
        return np.nan

    fn = os.path.join(DATA_DIR, f"{tkr}.csv")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    # append today’s IV (duplicate dates collapse later)
    pd.DataFrame([[today, iv_now]], columns=["date", "iv"]).to_csv(
        fn, mode="a", header=not os.path.exists(fn), index=False
    )

    # read last N days, drop duplicate dates
    iv_hist = pd.read_csv(fn).drop_duplicates("date").tail(lookback)["iv"]
    if iv_hist.empty or iv_hist.max() == iv_hist.min():
        return np.nan

    return (iv_now - iv_hist.min()) / (iv_hist.max() - iv_hist.min()) * 100

def calc_beta(ticker_returns: pd.Series) -> float:
    if _SPY_RET.empty or ticker_returns.empty:
        return np.nan
    return ticker_returns.cov(_SPY_RET) / _SPY_RET.var()

# ─────────────────────────── MAIN ───────────────────────────
def main():
    tickers = load_tickers()
    if not tickers:
        return

    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    rows = []

    for tk in tickers:
        hist = fetch_history(tk)
        if hist.empty:
            continue
        # --- IV & IV Rank --------------------------------------------
        iv_now   = current_iv(tk)
        iv_rank_pct = iv_rank(tk, iv_now)
        time.sleep(0.3)  # throttle to stay under free API limits

        adx, atr, sma20, sma50, sma200, rsi = calc_indicators(hist)
        beta = calc_beta(hist["Close"].pct_change().dropna())
        rows.append({
            "timestamp": ts,
            "ticker":    tk,
            "ADX":       adx,
            "ATR":       atr,
            "20dma":     sma20,
            "50dma":     sma50,
            "200dma":    sma200,
            "IV_rank":   iv_rank_pct,
            "RSI":       rsi,
            "beta_SPY":  beta
        })

    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)
    logging.info("Tech signals saved (%d tickers) → %s", len(rows), OUTPUT_CSV)

if __name__ == "__main__":
    main()
