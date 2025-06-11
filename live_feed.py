#!/usr/bin/env python3
"""
live_feed.py — Hybrid live‑quote snapshot (IBKR first, yfinance fallback)
------------------------------------------------------------------------

• Reads tickers from tickers_live.txt or tickers.txt
• Tries to pull real‑time top‑of‑book data via IBKR / TWS Gateway
• Any ticker that fails (or if Gateway is down) falls back to yfinance
• Output file gets a timestamped name:  live_quotes_YYYYMMDD_HHMM.csv

Columns:
    timestamp · ticker · last · bid · ask · open · high · low · prev_close · volume · unrealized_pnl · unrealized_pnl_pct · source
"""

import os
import sys
import time
import logging
import csv
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from typing import List, Dict
import numpy as np
import yfinance as yf

# optional progress bar
try:
    from tqdm import tqdm

    PROGRESS = True
except ImportError:
    PROGRESS = False

try:
    from pandas_datareader import data as web

    FRED_AVAILABLE = True
except ImportError:
    FRED_AVAILABLE = False


# ----------------------------------------------------------
# Try to import ib_insync; if unavailable we’ll silently skip
# ----------------------------------------------------------
try:
    from ib_insync import IB, Stock, Index, Future, Option

    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False

# Always‑included macro tickers
EXTRA_TICKERS = [
    # Treasury yields (intraday CBOE + FRED daily)
    "^IRX",
    "^FVX",
    "^TNX",
    "^TYX",  # 13‑w, 5‑y, 10‑y, 30‑y live
    "US2Y",
    "US10Y",
    "US20Y",
    "US30Y",  # daily constant‑maturity from FRED
    # Commodity front‑month futures
    "GC=F",
    "SI=F",
    "CL=F",
    "BZ=F",
    # Gold ETF
    "GLD",
]

# --------------------------- CONFIG ------------------------
PORTFOLIO_FILES = ["tickers_live.txt", "tickers.txt"]
TR_TZ = ZoneInfo("Europe/Istanbul")
now_tr = datetime.now(TR_TZ)
DATE_TAG = now_tr.strftime("%Y%m%d")
TIME_TAG = now_tr.strftime("%H%M")

# Save snapshots to iCloud Drive ▸ Downloads
OUTPUT_DIR = (
    "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

OUTPUT_CSV = os.path.join(OUTPUT_DIR, f"live_quotes_{DATE_TAG}_{TIME_TAG}.csv")
OUTPUT_POS_CSV = os.path.join(OUTPUT_DIR, f"live_positions_{DATE_TAG}_{TIME_TAG}.csv")

IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7497, 2  # separate clientId
IB_TIMEOUT = 4.0  # seconds to wait per batch

# yfinance proxy map for friendly tickers
PROXY_MAP = {
    "VIX": "^VIX",
    "VVIX": "^VVIX",
    "DXY": "DX-Y.NYB",
    # commodities / yields map to themselves (clarity)
    "GC=F": "GC=F",
    "SI=F": "SI=F",
    "CL=F": "CL=F",
    "BZ=F": "BZ=F",
    "US2Y=RR": "US2Y=RR",
    "US10Y=RR": "US10Y=RR",
    "US20Y=RR": "US20Y=RR",
    "US30Y=RR": "US30Y=RR",
    "^IRX": "^IRX",
    "^FVX": "^FVX",
}

YIELD_MAP = {"US2Y": "DGS2", "US10Y": "DGS10", "US20Y": "DGS20", "US30Y": "DGS30"}

# Index mapping for IBKR (futures removed; will fall back to yfinance)
SYMBOL_MAP = {
    "VIX": (Index, dict(symbol="VIX", exchange="CBOE")),
    "VVIX": (Index, dict(symbol="VVIX", exchange="CBOE")),
    "^TNX": (Index, dict(symbol="TNX", exchange="CBOE")),  # 10‑yr yield
    "^TYX": (Index, dict(symbol="TYX", exchange="CBOE")),  # 30‑yr yield
    "^IRX": (Index, dict(symbol="IRX", exchange="CBOE")),  # 13‑week yield
    "^FVX": (Index, dict(symbol="FVX", exchange="CBOE")),  # 5‑year yield
    # "^UST2Y": (Index, dict(symbol="UST2Y", exchange="CBOE")),
    # "^UST20Y": (Index, dict(symbol="UST20Y", exchange="CBOE")),
    # "XAUUSD=X": (Index, dict(symbol="XAUUSD", exchange="FOREX")),
    # "XAGUSD=X": (Index, dict(symbol="XAGUSD", exchange="FOREX")),
    # leave CL=F and BZ=F to fall back to yfinance (skip continuous futures)
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

# Silence ib_insync debug chatter
if "IB_AVAILABLE" in globals() and IB_AVAILABLE:
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


def fetch_ib_positions(ib: "IB") -> tuple[list[Option], set[str]]:
    """
    Return a list of *Option contracts currently held* plus the underlying
    symbols for those positions (to guarantee we snapshot them too).
    """
    opts: list[Option] = []
    underlyings: set[str] = set()
    try:
        positions = ib.positions()
        for p in positions:
            con = p.contract
            if con.secType == "OPT":
                opt = Option(
                    con.symbol,
                    con.lastTradeDateOrContractMonth,
                    con.strike,
                    con.right,
                    exchange=con.exchange or "SMART",
                    currency=con.currency or "USD",
                    multiplier=con.multiplier,
                    tradingClass=con.tradingClass,
                )
                opts.append(opt)
                underlyings.add(con.symbol.upper())
    except Exception as e:
        logging.warning("IB positions fetch failed: %s", e)
    return opts, underlyings


def fetch_ib_quotes(tickers: list[str], opt_cons: list[Option]) -> pd.DataFrame:
    """Return DataFrame of quotes for symbols IB can serve; missing ones flagged NaN."""
    if not IB_AVAILABLE:
        return pd.DataFrame()

    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CID, timeout=3)
    except Exception:
        logging.warning("IBKR Gateway not reachable — skipping IB pull.")
        return pd.DataFrame()

    combined_rows: list[dict] = []
    reqs: dict[str, any] = {}

    # Build contracts & request market data
    iterable = tqdm(tickers, desc="IB snapshots") if PROGRESS else tickers
    for tk in iterable:
        # Skip continuous futures (=F) and Yahoo-only yield symbols – use yfinance
        if tk.endswith("=F") or tk in YIELD_MAP:
            continue
        # Skip symbols IB cannot serve (metals spot & some yields)
        # if tk in {"XAUUSD=X", "XAGUSD=X", "^UST2Y", "^UST20Y"}:
        #     continue
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

    # ----- option contracts -----
    for opt in opt_cons:
        try:
            ql = ib.qualifyContracts(opt)
            if not ql:
                continue
            # Use a normal snapshot (regulatorySnapshot=False) to avoid 10170 permission errors
            md = ib.reqMktData(ql[0], "", False, False)
            reqs[opt.localSymbol] = md
        except Exception:
            continue

    ib.sleep(IB_TIMEOUT)

    for key, md in reqs.items():
        combined_rows.append(
            {
                "ticker": key,
                "last": (
                    md.last / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.last
                    else md.last
                ),
                "bid": (
                    md.bid / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.bid
                    else md.bid
                ),
                "ask": (
                    md.ask / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.ask
                    else md.ask
                ),
                "open": (
                    md.open / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.open
                    else md.open
                ),
                "high": (
                    md.high / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.high
                    else md.high
                ),
                "low": (
                    md.low / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.low
                    else md.low
                ),
                "prev_close": (
                    md.close / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.close
                    else md.close
                ),
                "volume": md.volume,
                "source": "IB",
            }
        )
        ib.cancelMktData(md.contract)

    ib.disconnect()
    return pd.DataFrame(combined_rows)


def fetch_yf_quotes(tickers: list[str]) -> pd.DataFrame:
    rows = []
    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    iterable = tqdm(tickers, desc="yfinance") if PROGRESS else tickers
    for t in iterable:
        if t in YIELD_MAP:
            continue  # yields fetched via FRED
        yf_tkr = PROXY_MAP.get(t, t)
        try:
            info = yf.Ticker(yf_tkr).info
            price = info.get("regularMarketPrice")
            bid = info.get("bid")
            ask = info.get("ask")
            day_high = info.get("dayHigh")
            day_low = info.get("dayLow")
            prev_close = info.get("previousClose")
            vol = info.get("volume")
        except Exception as e:
            # fallback to fast download (1d) if info API stalls
            try:
                hist = yf.download(yf_tkr, period="2d", interval="1d", progress=False)
                price = hist["Close"].iloc[-1] if not hist.empty else np.nan
                prev_close = hist["Close"].iloc[-2] if len(hist) > 1 else np.nan
                bid = ask = day_high = day_low = vol = np.nan
                logging.warning("yfinance info fail %s, used download(): %s", t, e)
            except Exception as e2:
                logging.warning("yfinance miss %s: %s", t, e2)
                continue
        # Yahoo yields like ^TNX return 10× the percentage; rescale
        if t in {"^IRX", "^FVX", "^TNX", "^TYX"} and price is not None:
            price = price / 10.0
        rows.append(
            {
                "ticker": t,
                "last": price,
                "bid": bid,
                "ask": ask,
                "open": info.get("open") if "info" in locals() else np.nan,
                "high": day_high,
                "low": day_low,
                "prev_close": prev_close,
                "volume": vol,
                "source": "YF",
            }
        )
        time.sleep(0.1)
    return pd.DataFrame(rows)


def fetch_fred_yields(tickers: list[str]) -> pd.DataFrame:
    if not FRED_AVAILABLE:
        return pd.DataFrame()
    rows = []
    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    iterable = tqdm(tickers, desc="FRED") if PROGRESS else tickers
    for t in iterable:
        series = YIELD_MAP.get(t)
        if not series:
            continue
        try:
            val = web.DataReader(series, "fred").iloc[-1].values[0]
            rows.append(
                {
                    "ticker": t,
                    "last": val,
                    "bid": np.nan,
                    "ask": np.nan,
                    "open": np.nan,
                    "high": np.nan,
                    "low": np.nan,
                    "prev_close": np.nan,
                    "volume": np.nan,
                    "source": "FRED",
                }
            )
        except Exception as e:
            logging.warning("FRED miss %s: %s", t, e)
    return pd.DataFrame(rows)


# -------------------- POSITION P&L SNAPSHOT --------------------
def fetch_live_positions(ib: "IB") -> pd.DataFrame:
    """
    Return a DataFrame with real‑time P&L for ALL open positions in the account.

    Columns: timestamp · symbol · secType · position · avg_cost · last ·
             market_value · cost_basis · unrealized_pnl · unrealized_pnl_pct
    """
    try:
        positions = ib.positions()
    except Exception as e:
        logging.warning("IB positions() failed: %s", e)
        return pd.DataFrame()

    rows: List[Dict] = []
    ts_now = datetime.now(TR_TZ).strftime("%Y-%m-%dT%H:%M:%S%z")

    # prepare market‑data requests
    md_reqs = {}
    for pos in positions:
        con = pos.contract
        try:
            (ql,) = ib.qualifyContracts(con)
            md = ib.reqMktData(ql, "", False, False)
            md_reqs[con.conId] = (con, md, pos.avgCost, pos.position)
        except Exception:
            continue

    ib.sleep(IB_TIMEOUT)  # allow quotes to update

    for conId, (con, md, avg_cost, qty) in md_reqs.items():
        last = md.last or md.close or np.nan
        mult = int(con.multiplier) if con.multiplier else 1
        cost_basis = avg_cost * qty * mult
        market_val = last * qty * mult
        unreal_pnl = (last - avg_cost) * qty * mult
        unreal_pct = (unreal_pnl / cost_basis * 100) if cost_basis else np.nan
        rows.append(
            {
                "timestamp": ts_now,
                "symbol": con.symbol,
                "secType": con.secType,
                "position": qty,
                "avg_cost": avg_cost,
                "last": last,
                "market_value": market_val,
                "cost_basis": cost_basis,
                "unrealized_pnl_pct": unreal_pct,
                "unrealized_pnl": unreal_pnl,
            }
        )
        ib.cancelMktData(md.contract)

    return pd.DataFrame(rows)


# -------------------------- MAIN ---------------------------
def main():
    parser = argparse.ArgumentParser(description="Snapshot live quotes")
    parser.add_argument(
        "--txt",
        action="store_true",
        help="Save a plain text copy alongside the CSV files.",
    )
    args = parser.parse_args()

    tickers = load_tickers()
    opt_list, opt_under = ([], set())
    if IB_AVAILABLE:
        ib_tmp = IB()
        try:
            ib_tmp.connect(IB_HOST, IB_PORT, clientId=99, timeout=3)
            opt_list, opt_under = fetch_ib_positions(ib_tmp)
            ib_tmp.disconnect()
        except Exception:
            pass
    tickers = sorted(set(tickers + list(opt_under) + EXTRA_TICKERS))

    if not tickers:
        return

    ts_now = datetime.now(TR_TZ).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    df_ib = fetch_ib_quotes(tickers, opt_list)
    served = set(df_ib["ticker"]) if not df_ib.empty else set()
    remaining = [t for t in tickers if t not in served and t not in YIELD_MAP]

    df_yf = fetch_yf_quotes(remaining) if remaining else pd.DataFrame()

    remaining_yields = [t for t in remaining if t in YIELD_MAP]
    df_fred = (
        fetch_fred_yields(remaining_yields) if remaining_yields else pd.DataFrame()
    )

    df = pd.concat([df_ib, df_yf, df_fred], ignore_index=True)
    df.insert(0, "timestamp", ts_now)
    # --- live positions snapshot & unrealized PnL merge -----------
    pnl_map = {}
    pct_map = {}
    if IB_AVAILABLE:
        ib_live = IB()
        try:
            ib_live.connect(IB_HOST, IB_PORT, clientId=98, timeout=3)
            df_pos = fetch_live_positions(ib_live)
            ib_live.disconnect()
            if not df_pos.empty:
                df_pos.to_csv(
                    OUTPUT_POS_CSV,
                    index=False,
                    quoting=csv.QUOTE_MINIMAL,
                    float_format="%.3f",
                )
                if args.txt:
                    with open(OUTPUT_POS_CSV.replace(".csv", ".txt"), "w") as fh:
                        fh.write(
                            df_pos.to_string(
                                index=False, float_format=lambda x: f"{x:.3f}"
                            )
                        )
                logging.info(
                    "Saved %d live positions → %s", len(df_pos), OUTPUT_POS_CSV
                )

                # aggregate unrealized PnL AND cost basis by underlying symbol
                pnl_map = df_pos.groupby("symbol")["unrealized_pnl"].sum().to_dict()
                cost_map = df_pos.groupby("symbol")["cost_basis"].sum().to_dict()
                pct_map = {
                    s: (100 * pnl_map[s] / cost_map[s]) if cost_map[s] else np.nan
                    for s in pnl_map
                }
        except Exception as e:
            logging.warning("Live position snapshot failed: %s", e)

    # map per-symbol PnL onto the quote rows
    df["unrealized_pnl"] = df["ticker"].map(pnl_map)
    df["unrealized_pnl_pct"] = df["ticker"].map(pct_map)

    # reorder columns for clarity
    quote_cols = [
        "timestamp",
        "ticker",
        "last",
        "bid",
        "ask",
        "open",
        "high",
        "low",
        "prev_close",
        "volume",
        "unrealized_pnl",
        "unrealized_pnl_pct",
        "source",
    ]
    df = df[[c for c in quote_cols if c in df.columns]]

    df.to_csv(
        OUTPUT_CSV,
        index=False,
        quoting=csv.QUOTE_MINIMAL,
        float_format="%.3f",
    )
    if args.txt:
        with open(OUTPUT_CSV.replace(".csv", ".txt"), "w") as fh:
            fh.write(df.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    logging.info("Saved %d quotes → %s", len(df), OUTPUT_CSV)


if __name__ == "__main__":
    main()
