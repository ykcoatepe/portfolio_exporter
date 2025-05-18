#!/usr/bin/env python3
"""
live_feed.py — Hybrid live‑quote snapshot (IBKR first, yfinance fallback)
------------------------------------------------------------------------

• Reads tickers from tickers_live.txt or tickers.txt
• Tries to pull real‑time top‑of‑book data via IBKR / TWS Gateway
• Any ticker that fails (or if Gateway is down) falls back to yfinance
• Output file gets a timestamped name:  live_quotes_YYYYMMDD_HHMM.csv

Columns:
    timestamp · ticker · last · bid · ask · open · high · low · prev_close · volume · source
"""

import os, sys, time, logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import numpy as np
import yfinance as yf


# ----------------------------------------------------------
# Try to import ib_insync; if unavailable we’ll silently skip
# ----------------------------------------------------------
try:
    from ib_insync import IB, Stock, Index, Future
    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False

# --------------------------- CONFIG ------------------------
PORTFOLIO_FILES = ["tickers_live.txt", "tickers.txt"]
TR_TZ = ZoneInfo("Europe/Istanbul")
now_tr = datetime.now(TR_TZ)
DATE_TAG = now_tr.strftime("%Y%m%d")
TIME_TAG = now_tr.strftime("%H%M")
OUTPUT_CSV = f"live_quotes_{DATE_TAG}_{TIME_TAG}.csv"

IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7497, 2     # separate clientId
IB_TIMEOUT = 4.0                                     # seconds to wait per batch

# yfinance proxy map for friendly tickers
PROXY_MAP = {
    "VIX":  "^VIX",
    "VVIX": "^VVIX",
    "DXY":  "DX-Y.NYB"
}

# Index mapping for IBKR (futures removed; will fall back to yfinance)
SYMBOL_MAP = {
    "VIX":  (Index,  dict(symbol="VIX",  exchange="CBOE")),
    "VVIX": (Index,  dict(symbol="VVIX", exchange="CBOE")),
    "^TNX": (Index,  dict(symbol="TNX",  exchange="CBOE")),   # 10‑yr yield
    "^TYX": (Index,  dict(symbol="TYX",  exchange="CBOE")),   # 30‑yr yield
    # Remove futures from IB pull – they will fall back to yfinance
}

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")

# Silence ib_insync debug chatter
if 'IB_AVAILABLE' in globals() and IB_AVAILABLE:
    for _n in ("ib_insync.client", "ib_insync.wrapper", "ib_insync.ib"):
        lg = logging.getLogger(_n)
        lg.setLevel(logging.WARNING)
        lg.propagate = False

# ------------------------ HELPERS --------------------------
def load_tickers() -> list[str]:
    p = next((f for f in PORTFOLIO_FILES if os.path.exists(f)), None)
    if not p:
        logging.error("No ticker file found.")
        return []
    with open(p) as f:
        return [ln.strip().upper() for ln in f if ln.strip()]

def fetch_ib_quotes(tickers: list[str]) -> pd.DataFrame:
    """Return DataFrame of quotes for symbols IB can serve; missing ones flagged NaN."""
    if not IB_AVAILABLE:
        return pd.DataFrame()

    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CID, timeout=3)
    except Exception:
        logging.warning("IBKR Gateway not reachable — skipping IB pull.")
        return pd.DataFrame()

    rows, reqs = [], {}

    # Build contracts & request market data
    for tk in tickers:
        # Skip generic continuous futures (e.g. GC=F) – will fall back to yfinance
        if tk.endswith("=F"):
            continue
        if tk in SYMBOL_MAP:
            cls, kw = SYMBOL_MAP[tk]
            con = cls(**kw)
        else:
            con = Stock(tk, "SMART", "USD")
        try:
            ql = ib.qualifyContracts(con)
            if not ql:
                raise ValueError("not qualified")
            md = ib.reqMktData(ql[0], "", False, False)
            reqs[tk] = md
        except Exception:
            continue  # will fall back to yfinance later

    ib.sleep(IB_TIMEOUT)

    for tk, md in reqs.items():
        rows.append({
            "ticker":     tk,
            "last":       md.last,
            "bid":        md.bid,
            "ask":        md.ask,
            "open":       md.open,
            "high":       md.high,
            "low":        md.low,
            "prev_close": md.close,
            "volume":     md.volume,
            "source":     "IB"
        })
        ib.cancelMktData(md.contract)

    ib.disconnect()
    return pd.DataFrame(rows)

def fetch_yf_quotes(tickers: list[str]) -> pd.DataFrame:
    rows = []
    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for t in tickers:
        yf_tkr = PROXY_MAP.get(t, t)
        try:
            info = yf.Ticker(yf_tkr).info
            rows.append({
                "ticker":     t,
                "last":       info.get("regularMarketPrice"),
                "bid":        info.get("bid"),
                "ask":        info.get("ask"),
                "open":       info.get("open"),
                "high":       info.get("dayHigh"),
                "low":        info.get("dayLow"),
                "prev_close": info.get("previousClose"),
                "volume":     info.get("volume"),
                "source":     "YF"
            })
        except Exception as e:
            logging.warning("yfinance miss %s: %s", t, e)
    return pd.DataFrame(rows)

# -------------------------- MAIN ---------------------------
def main():
    tickers = load_tickers()
    if not tickers:
        return

    ts_now = datetime.now(TR_TZ).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    df_ib  = fetch_ib_quotes(tickers)
    served  = set(df_ib["ticker"]) if not df_ib.empty else set()
    remaining = [t for t in tickers if t not in served]

    df_yf = fetch_yf_quotes(remaining) if remaining else pd.DataFrame()

    df = pd.concat([df_ib, df_yf], ignore_index=True)
    df.insert(0, "timestamp", ts_now)
    df.to_csv(OUTPUT_CSV, index=False)
    logging.info("Saved %d quotes → %s", len(df), OUTPUT_CSV)

if __name__ == "__main__":
    main()
