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
from portfolio_exporter.core.config import settings
import sys
import time
import logging
import csv
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from typing import List, Dict, Any
from portfolio_exporter.core.ui import run_with_spinner
import numpy as np
import math


# ------------------------------------------------------------------
# Helper to normalize prices: IB sometimes returns -1 for no‑quote
# ------------------------------------------------------------------
def _clean_price(val):
    """Return np.nan for None/‑1 placeholders, otherwise the value."""
    return np.nan if val in (None, -1) else val


import yfinance as yf

# Robust session with retries/backoff to reduce empty/NaN responses from Yahoo
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    _yf_session = requests.Session()
    _yf_retries = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.25,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
    )
    _yf_adapter = HTTPAdapter(
        max_retries=_yf_retries, pool_connections=10, pool_maxsize=10
    )
    _yf_session.mount("https://", _yf_adapter)
    _yf_session.mount("http://", _yf_adapter)
    try:
        import yfinance.shared as _yf_shared

        _yf_shared._DEFAULT_SESSION = _yf_session
    except Exception:
        pass
except Exception:
    _yf_session = None


# ---------- helpers -------------------------------------------------
def _first_valid(*vals):
    """
    Return the first value that is neither None nor NaN.
    Treats float('nan') / numpy.nan as missing, same as None.
    """
    for v in vals:
        if v is None:
            continue
        if isinstance(v, (float, np.floating)) and math.isnan(v):
            continue
        return v
    return None


def _yf_resolve_last_price(
    yf_symbol: str,
    label: str | None = None,
    info: Dict[str, Any] | None = None,
    fast: Dict[str, Any] | None = None,
) -> float:
    """
    Best-effort ladder to resolve a last price from Yahoo Finance.

    Order:
    1) Provided info/fast_info values (regular + pre-market + previous close)
    2) 1m intraday bar, then 5m
    3) 2d daily bar last close
    4) 5d history last valid close
    5) previousClose via info
    6) 1y history last valid close
    Returns float or NaN.
    """
    try:
        tk = yf.Ticker(yf_symbol)
        if fast is None:
            try:
                fast = tk.fast_info or {}
            except Exception:
                fast = {}
        # Step 1: info/fast
        price = _first_valid(
            (info or {}).get("regularMarketPrice"),
            (info or {}).get("preMarketPrice"),
            fast.get("last_price"),
            fast.get("lastPrice"),
            fast.get("previous_close"),
            fast.get("previousClose"),
            (info or {}).get("previousClose"),
        )
        # Step 2: intraday 1m
        if price is None or pd.isna(price):
            try:
                intr = yf.download(yf_symbol, period="1d", interval="1m", progress=False)
                if intr is not None and not intr.empty:
                    price = float(intr["Close"].dropna().iloc[-1])
            except Exception:
                pass
        # Step 3: intraday 5m
        if price is None or pd.isna(price):
            try:
                intr5 = yf.download(yf_symbol, period="1d", interval="5m", progress=False)
                if intr5 is not None and not intr5.empty:
                    price = float(intr5["Close"].dropna().iloc[-1])
            except Exception:
                pass
        # Step 4: 2d daily
        if price is None or pd.isna(price):
            try:
                daily = yf.download(yf_symbol, period="2d", interval="1d", progress=False)
                if daily is not None and not daily.empty:
                    price = float(daily["Close"].dropna().iloc[-1])
            except Exception:
                pass
        # Step 5: 5d history
        if price is None or pd.isna(price):
            try:
                hist5 = tk.history(period="5d", interval="1d")
                if hist5 is not None and not hist5.empty:
                    close_vals = hist5["Close"].dropna()
                    if not close_vals.empty:
                        price = float(close_vals.iloc[-1])
            except Exception:
                pass
        # Step 6: previousClose via info (if not provided)
        if price is None or pd.isna(price):
            try:
                inf = info if info is not None else tk.info
                pc = inf.get("previousClose") if isinstance(inf, dict) else None
                if pc is not None and not pd.isna(pc):
                    price = float(pc)
            except Exception:
                pass
        # Step 7: 1y history last valid close
        if price is None or pd.isna(price):
            try:
                hist1y = tk.history(period="1y", interval="1d")
                if hist1y is not None and not hist1y.empty:
                    close_vals = hist1y["Close"].dropna()
                    if not close_vals.empty:
                        price = float(close_vals.iloc[-1])
            except Exception as e:
                if label:
                    logging.warning("1y history fallback failed for %s: %s", label, e)
        return price if price is not None else float("nan")
    except Exception as e:
        if label:
            logging.warning("yfinance resolution failed for %s: %s", label, e)
        return float("nan")


# optional PDF dependencies
try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
except Exception:  # pragma: no cover - optional
    SimpleDocTemplate = Table = TableStyle = colors = letter = landscape = None

# optional progress bar
try:
    from utils.progress import iter_progress

    PROGRESS = True
except Exception:  # pragma: no cover - optional
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

# Tickers always included in live snapshots
ALWAYS_TICKERS = ["SPY", "QQQ", "IWM", "DIA", "VIX"]

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
OUTPUT_DIR = os.path.expanduser(settings.output_dir)

OUTPUT_CSV = os.path.join(OUTPUT_DIR, f"live_quotes_{DATE_TAG}_{TIME_TAG}.csv")
OUTPUT_POS_CSV = os.path.join(OUTPUT_DIR, f"live_positions_{DATE_TAG}_{TIME_TAG}.csv")

from portfolio_exporter.core.ib_config import HOST as IB_HOST, PORT as IB_PORT, client_id as _cid
IB_CID = _cid("live_feed", default=2)  # separate clientId
IB_TIMEOUT = 4.0  # seconds to wait per batch

# yfinance proxy map for friendly tickers
PROXY_MAP = {
    # Explicit Yahoo symbol mappings for stubborn tickers
    "VIX": "^VIX",  # CBOE Volatility Index
    "RSP": "RSP",
    "VCSH": "VCSH",
    "TFLO": "TFLO",
    "KRBN": "KRBN",
    "MCD": "MCD",
    "PG": "PG",
    "PLD": "PLD",
    # Other known mappings and passthroughs
    "VVIX": "^VVIX",
    "DXY": "DX-Y.NYB",
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
    """Load tickers from the first portfolio file found.

    Preference: files under ``settings.output_dir``; then current directory.
    """
    candidates = [
        os.path.join(os.path.expanduser(settings.output_dir), name)
        for name in PORTFOLIO_FILES
    ] + PORTFOLIO_FILES
    p = next((f for f in candidates if os.path.exists(f)), None)
    if not p:
        logging.error("No ticker file found.")
        return []
    with open(p) as f:
        return [ln.strip().upper() for ln in f if ln.strip()]


def _load_portfolio_tickers() -> list[str]:
    """Wrapper for tests to load portfolio tickers."""
    return load_tickers()


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
    iterable = iter_progress(tickers, "IB snapshots") if PROGRESS else tickers
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
        last_price = _clean_price(
            md.last
            if md.last is not None
            else md.close  # fallback to close if last missing
        )
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

    df_ib = pd.DataFrame(combined_rows)
    # ------------------------------------------------------------------
    # Only count as “served” the rows that have a real quote.
    # Return df; caller will fall back to yfinance for the rest.
    # ------------------------------------------------------------------
    return df_ib


def fetch_yf_quotes(tickers: list[str]) -> pd.DataFrame:
    rows = []
    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    iterable = iter_progress(tickers, "yfinance") if PROGRESS else tickers
    for t in iterable:
        if t in YIELD_MAP:
            continue  # yields fetched via FRED
        yf_tkr = PROXY_MAP.get(t, t)
        try:
            info = yf.Ticker(yf_tkr).info
            # fast_info is more reliable after hours – use it to back-fill gaps
            fast = yf.Ticker(yf_tkr).fast_info or {}
            price = _yf_resolve_last_price(yf_tkr, label=t, info=info, fast=fast)
            bid = _first_valid(fast.get("bid"), fast.get("bid_price"), info.get("bid"))
            ask = _first_valid(fast.get("ask"), fast.get("ask_price"), info.get("ask"))
            day_high = _first_valid(fast.get("day_high"), fast.get("dayHigh"))
            day_low = _first_valid(fast.get("day_low"), fast.get("dayLow"))
            prev_close = _first_valid(
                fast.get("previous_close"),
                fast.get("previousClose"),
                info.get("previousClose"),
            )
            vol = _first_valid(
                fast.get("last_volume"), fast.get("volume"), info.get("volume")
            )
        except Exception as e:
            logging.warning("yfinance info fail %s: %s", t, e)
            bid = ask = day_high = day_low = vol = np.nan
            prev_close = np.nan
            price = _yf_resolve_last_price(yf_tkr, label=t)
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
    df = pd.DataFrame(rows)
    return df


def fetch_fred_yields(tickers: list[str]) -> pd.DataFrame:
    if not FRED_AVAILABLE:
        return pd.DataFrame()
    rows = []
    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    iterable = iter_progress(tickers, "FRED") if PROGRESS else tickers
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

    Columns: timestamp · ticker · secType · position · avg_cost · last ·
             market_value · cost_basis · unrealized_pnl · unrealized_pnl_pct
             (combo positions are labeled as OPT_COMBO – detected either as BAG or multi‑leg heuristics)
    """
    try:
        positions = ib.positions()
    except Exception as e:
        logging.warning("IB positions() failed: %s", e)
        return pd.DataFrame()

    rows: List[Dict] = []
    ts_now = datetime.now(TR_TZ).strftime("%Y-%m-%dT%H:%M:%S%z")

    # --- simple combo heuristic -----------------------------------------
    # If there is more than one option position with the same underlying
    # symbol *and* expiry date, treat those legs as belonging to a combo.
    combo_counts: dict[tuple[str, str], int] = {}
    for pos in positions:
        c = pos.contract
        if c.secType == "OPT":
            key = (c.symbol, getattr(c, "lastTradeDateOrContractMonth", ""))
            combo_counts[key] = combo_counts.get(key, 0) + 1

    # Collect conIds of all individual legs that are part of a combo
    combo_leg_con_ids = set()
    for pos in positions:
        if pos.contract.secType == "BAG" and pos.contract.comboLegs:
            for leg in pos.contract.comboLegs:
                combo_leg_con_ids.add(leg.conId)

    # prepare market‑data requests
    md_reqs = {}
    for pos in positions:
        con = pos.contract
        # Skip individual legs that are part of a combo
        if con.conId in combo_leg_con_ids:
            continue

        try:
            (ql,) = ib.qualifyContracts(con)
            md = ib.reqMktData(ql, "", False, False)
            md_reqs[con.conId] = (con, md, pos.avgCost, pos.position)
        except Exception:
            continue

    ib.sleep(IB_TIMEOUT)  # allow quotes to update

    for conId, (con, md, avg_cost, qty) in md_reqs.items():
        raw_last = (
            _clean_price(md.last) if md.last is not None else _clean_price(md.close)
        )
        last = raw_last
        mult = int(con.multiplier) if con.multiplier else 1
        cost_basis = avg_cost * qty * mult
        market_val = last * qty * mult
        unreal_pnl = (last - avg_cost) * qty * mult
        unreal_pct = (unreal_pnl / cost_basis * 100) if cost_basis else np.nan

        combo_legs_data = []
        if con.secType == "BAG" and con.comboLegs:
            from ib_insync import Contract

            for leg in con.comboLegs:
                leg_contract = ib.qualifyContracts(
                    Contract(conId=leg.conId, exchange=leg.exchange)
                )[0]
                combo_legs_data.append(
                    {
                        "symbol": leg_contract.symbol,
                        "sec_type": leg_contract.secType,
                        "expiry": getattr(
                            leg_contract, "lastTradeDateOrContractMonth", None
                        ),
                        "strike": getattr(leg_contract, "strike", None),
                        "right": getattr(leg_contract, "right", None),
                        "ratio": leg.ratio,
                        "action": leg.action,
                        "exchange": leg.exchange,
                    }
                )

        rows.append(
            {
                "timestamp": ts_now,
                "ticker": con.symbol,
                # Mark as OPT_COMBO if it's a BAG *or* detected multi‑leg set
                "secType": (
                    "OPT_COMBO"
                    if (
                        con.secType == "BAG"
                        or (
                            con.secType == "OPT"
                            and combo_counts.get(
                                (
                                    con.symbol,
                                    getattr(con, "lastTradeDateOrContractMonth", ""),
                                ),
                                0,
                            )
                            > 1
                        )
                    )
                    else con.secType
                ),
                "position": qty,
                "avg_cost": avg_cost,
                "last": last,
                "market_value": market_val,
                "cost_basis": cost_basis,
                "unrealized_pnl_pct": unreal_pct,
                "unrealized_pnl": unreal_pnl,
                "combo_legs": combo_legs_data if combo_legs_data else None,
            }
        )
        ib.cancelMktData(md.contract)

    return pd.DataFrame(rows)


def save_to_pdf(df: pd.DataFrame, path: str) -> None:
    # reportlab's Table object renders text directly, making the PDF text-based and searchable.
    if SimpleDocTemplate is None:
        raise RuntimeError("reportlab is required for PDF output")

    if "combo_legs" in df.columns:
        df["combo_legs"] = df["combo_legs"].apply(
            lambda x: (
                "\n".join(
                    [
                        f"{leg['ratio']}x {leg['action']} {leg['symbol']} ({leg['sec_type']}) "
                        f"Exp: {leg['expiry'] or 'N/A'}, Strike: {leg['strike'] or 'N/A'}, Right: {leg['right'] or 'N/A'}"
                        for leg in x
                    ]
                )
                if x
                else None
            )
        )

    # ---------- pretty‑format numbers & NaNs ---------------------
    display_df = df.copy()
    num_cols = display_df.select_dtypes(include=["number"]).columns
    for col in num_cols:
        display_df[col] = display_df[col].apply(
            lambda x: "—" if pd.isna(x) else f"{x:,.2f}"
        )
    rows_data = [display_df.columns.tolist()] + display_df.values.tolist()
    doc = SimpleDocTemplate(
        path,
        pagesize=landscape(letter),
        rightMargin=18,
        leftMargin=18,
        topMargin=18,
        bottomMargin=18,
    )
    table = Table(rows_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8,
                ),  # Increased font size for better readability
                ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
            ]
        )
    )
    doc.build([table])


def _current_output_paths() -> tuple[str, str]:
    """Compute fresh, timestamped output base paths for quotes and positions."""
    now = datetime.now(TR_TZ)
    date_tag = now.strftime("%Y%m%d")
    time_tag = now.strftime("%H%M")
    # Ensure output directory exists at write-time (avoid import-time side effects)
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    except Exception:
        pass
    base_q = os.path.join(OUTPUT_DIR, f"live_quotes_{date_tag}_{time_tag}")
    base_pos = os.path.join(OUTPUT_DIR, f"live_positions_{date_tag}_{time_tag}")
    return base_q, base_pos


def run(fmt: str = "csv", include_indices: bool = True, return_df: bool = False):
    """Programmatic entrypoint used by the Live-Market menu.

    - Avoids interactive prompts
    - Supports fmt in {csv, excel, pdf}
    - Optionally excludes macro/index extras if include_indices=False
    """
    # ----- resolve tickers -----
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
    extras = (ALWAYS_TICKERS + EXTRA_TICKERS) if include_indices else []
    tickers = sorted(set(tickers + list(opt_under) + extras))
    if not tickers:
        logging.warning("No tickers to snapshot.")
        return pd.DataFrame() if return_df else None

    ts_now = datetime.now(TR_TZ).strftime("%Y-%m-%dT%H:%M:%S%z")

    # ----- quotes from IB, YF, FRED -----
    df_ib = fetch_ib_quotes(tickers, opt_list)
    served = set(df_ib.loc[~df_ib["last"].isna(), "ticker"]) if not df_ib.empty else set()
    remaining = [t for t in tickers if t not in served]
    remaining_yields = [t for t in remaining if t in YIELD_MAP]
    remaining = [t for t in remaining if t not in YIELD_MAP]
    df_yf = fetch_yf_quotes(remaining) if remaining else pd.DataFrame()
    df_fred = fetch_fred_yields(remaining_yields) if remaining_yields else pd.DataFrame()
    df = pd.concat([df_ib, df_yf, df_fred], ignore_index=True)
    df.insert(0, "timestamp", ts_now)

    # ----- positions & unrealized PnL merge -----
    pnl_map: dict[str, float] = {}
    pct_map: dict[str, float] = {}
    df_pos = pd.DataFrame()
    if IB_AVAILABLE:
        ib_live = IB()
        try:
            ib_live.connect(IB_HOST, IB_PORT, clientId=98, timeout=3)
            df_pos = fetch_live_positions(ib_live)
            ib_live.disconnect()
            if not df_pos.empty:
                pnl_map = df_pos.groupby("ticker")["unrealized_pnl"].sum().to_dict()
                cost_map = df_pos.groupby("ticker")["cost_basis"].sum().to_dict()
                pct_map = {
                    s: (100 * pnl_map[s] / cost_map[s]) if cost_map[s] else np.nan
                    for s in pnl_map
                }
        except Exception as e:
            logging.warning("Live position snapshot failed: %s", e)

    df["unrealized_pnl"] = df["ticker"].map(pnl_map)
    df["unrealized_pnl_pct"] = df["ticker"].map(pct_map)

    if return_df:
        return df
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

    # ----- save outputs -----
    base_q, base_pos = _current_output_paths()
    fmt = (fmt or "csv").lower()
    if fmt == "pdf":
        save_to_pdf(df, base_q + ".pdf")
        if not df_pos.empty:
            save_to_pdf(df_pos, base_pos + ".pdf")
    elif fmt in {"xlsx", "excel"}:
        out_q = base_q + ".xlsx"
        with pd.ExcelWriter(out_q, engine="xlsxwriter") as writer:
            df.to_excel(writer, sheet_name="Quotes", index=False)
        if not df_pos.empty:
            out_p = base_pos + ".xlsx"
            with pd.ExcelWriter(out_p, engine="xlsxwriter") as writer:
                df_pos.to_excel(writer, sheet_name="Positions", index=False)
        logging.info("Saved live snapshot → %s", out_q)
    else:  # csv
        out_q = base_q + ".csv"
        df.to_csv(out_q, index=False, quoting=csv.QUOTE_MINIMAL, float_format="%.3f")
        if not df_pos.empty:
            out_p = base_pos + ".csv"
            df_pos.to_csv(
                out_p, index=False, quoting=csv.QUOTE_MINIMAL, float_format="%.3f"
            )
        logging.info("Saved live snapshot → %s", out_q)


# -------------------------- MAIN ---------------------------
def main():
    parser = argparse.ArgumentParser(description="Snapshot live quotes")
    parser.add_argument(
        "--txt",
        action="store_true",
        help="Save a plain text copy alongside the output file.",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Save a PDF instead of CSV.",
    )
    # Ignore any extra args when invoked from a parent menu
    args, _ = parser.parse_known_args()

    # Interactive choice only for direct CLI use
    fmt = "pdf" if args.pdf else "csv"
    if not args.pdf:
        try:
            choice = input("Output format [csv/pdf] (default csv): ").strip().lower()
        except EOFError:
            choice = ""
        if choice in {"pdf", "csv"}:
            fmt = choice

    # Defer to run() so menu and CLI share behavior
    run(fmt=fmt, include_indices=True)


### Removed legacy lightweight run() in favor of unified run() above.
def _snapshot_quotes(tickers: list[str], fmt: str = "csv") -> pd.DataFrame:
    """Return a minimal snapshot quotes DataFrame with columns [symbol, price].

    Uses yfinance ladder via _yf_resolve_last_price; IBKR path is handled in
    upstream helpers. Designed to be test-friendly and offline-capable.
    """
    rows = []
    for t in tickers:
        try:
            price = _yf_resolve_last_price(t)
        except Exception:
            price = float("nan")
        rows.append({"symbol": t, "price": float(price) if price is not None else float("nan")})
    return pd.DataFrame(rows)
