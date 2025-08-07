#!/usr/bin/env python3
"""
portfolio_greeks.py  –  Export per-position option Greeks and account-level totals

• Pulls current positions from the connected IBKR account.
• Requests market data streams for options to retrieve Greeks and IV.
• Computes *exposure* greeks → raw greek × contract multiplier × position size.
• Produces **two** CSV files in the Downloads folder:
    1. portfolio_greeks_<YYYYMMDD_HHMM>.csv          – one row per contract / underlying.
    2. portfolio_greeks_totals_<YYYYMMDD_HHMM>.csv   – a single row with summed totals.

Usage
=====
$ python portfolio_greeks.py                       # full portfolio (writes to default output directory)
$ python portfolio_greeks.py --output-dir .        # write CSVs to current directory
$ python portfolio_greeks.py --symbols MSFT,QQQ    # restrict to subset
"""

import argparse
import csv
import logging
from portfolio_exporter.core.config import settings
import math
import os
import sys
import json
import requests
import calendar
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Tuple
from pathlib import Path

from utils.bs import bs_greeks
from legacy.option_chain_snapshot import fetch_yf_open_interest
from portfolio_exporter.core.ui import run_with_spinner
from portfolio_exporter.core.combo import detect_combos

import numpy as np
import pandas as pd

try:  # optional dependency
    import xlsxwriter  # type: ignore
except Exception:  # pragma: no cover - optional
    xlsxwriter = None  # type: ignore

# PDF export dependencies
try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
except Exception:  # pragma: no cover - optional
    SimpleDocTemplate = Table = TableStyle = colors = letter = landscape = None

from ib_insync import Future, IB, Index, Option, Position, Stock, Ticker, util
from ib_insync.contract import Contract

try:
    from utils.progress import iter_progress

    # Re‑enable progress‑bar printing
    PROGRESS = True
except Exception:  # pragma: no cover - optional
    PROGRESS = False

# ────────────────────── logging setup (must precede helpers) ─────────────────────
LOG_FMT = "%(asctime)s %(levelname)s %(name)s %(message)s"
# Default to WARNING to keep console noise down
logging.basicConfig(level=logging.WARNING, format=LOG_FMT)
logger = logging.getLogger(__name__)
# Silence verbose ib_insync chatter – only show truly critical issues
for _n in ("ib_insync", "ib_insync.ib", "ib_insync.wrapper"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)

# ─────────────────────────  draw-down helpers  ──────────────────────────


def _running_drawdown(path: pd.Series) -> pd.Series:
    """
    Running percentage draw-down from the cumulative peak of the series.
    """
    cum_max = path.cummax()
    return (cum_max - path) / cum_max


# ───────────────────── NAV bootstrap via Client Portal ─────────────────────

CP_URL = "https://localhost:5000/v1/pa/performance"
IB_ACCOUNT = os.getenv("IB_ACCOUNT") or "U4380392"


def bootstrap_nav(ib: "IB", days: int = 365) -> pd.Series:
    """
    Try to fetch historical NetLiq series in order of preference:
    1) Client-Portal REST (all available history)
    2) API reqPnL fallback (365 days)
    Returns pd.Series indexed by date or empty series on failure.
    """
    # ---- 1) Client-Portal REST ----
    try:
        parms = {"period": "all", "fields": "nav"}
        resp = requests.get(
            f"{CP_URL}/{IB_ACCOUNT}", params=parms, verify=False, timeout=20
        )
        resp.raise_for_status()
        data = resp.json().get("nav", [])
        ks = ("value", "nav")
        nav_dict = {
            pd.to_datetime(r["date"]): next(r[k] for k in ks if k in r)
            for r in data
            if any(k in r for k in ks)
        }
        series = pd.Series(nav_dict, dtype=float).sort_index()
        if not series.empty:
            logger.info(f"Bootstrapped NAV from REST – {len(series)} rows.")
            return series
    except Exception as exc:
        logger.warning(f"REST NAV fetch failed: {exc}")

    # ---- 2) reqPnL fallback (365 days) ----
    try:
        pnl_obj = ib.reqPnL(IB_ACCOUNT, modelCode="", accountCode="")
        # allow stream to populate
        ib.sleep(2)
        if pnl_obj.dailyPnLSeries:
            pnl_df = pd.DataFrame(pnl_obj.dailyPnLSeries)
            # pnl_df has columns date, dailyPnL, unrealizedPnL, realizedPnL, value
            series = (
                pnl_df.assign(date=lambda d: pd.to_datetime(d.date))
                .set_index("date")["value"]
                .astype(float)
                .sort_index()
            )
        else:
            series = pd.Series(dtype=float)
        ib.cancelPnL(pnl_obj.reqId)
        if not series.empty:
            logger.info(f"Bootstrapped NAV from reqPnL – {len(series)} rows.")
            return series
    except Exception as exc:
        logger.warning(f"reqPnL NAV fetch failed: {exc}")

    return pd.Series(dtype=float)


def eddr(
    path: pd.Series, horizon_days: int = 252, alpha: float = 0.99
) -> tuple[float, float]:
    """
    Extreme Downside Draw-down Risk (DaR & CDaR).

    Parameters
    ----------
    path : pd.Series
        Daily net-liq / NAV indexed by date.
    horizon_days : int
        Look-back window (rolling) for maximum draw-down.
    alpha : float
        Tail quantile (e.g. 0.99 → 99-percent extreme).

    Returns
    -------
    tuple (dar, cdar)
        dar  – DaR₍α₎
        cdar – Conditional DaR, mean draw-down beyond DaR.
    """
    window_dd = (
        path.rolling(window=horizon_days, min_periods=horizon_days)
        .apply(lambda w: _running_drawdown(w).max(), raw=False)
        .dropna()
    )
    if window_dd.empty:
        return np.nan, np.nan

    dar_val = float(np.quantile(window_dd, alpha))
    cdar_val = float(window_dd[window_dd >= dar_val].mean())
    return dar_val, cdar_val


# ───────────────────────── CONFIG ──────────────────────────

OUTPUT_DIR = os.path.expanduser(settings.output_dir)
os.makedirs(OUTPUT_DIR, exist_ok=True)

NAV_LOG = Path(os.path.join(OUTPUT_DIR, "nav_history.csv"))

IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7497, 11  # separate clientId from snapshots

# contract multipliers by secType (IB doesn't always fill this field)
DEFAULT_MULT = {
    "OPT": 100,
    "FOP": 50,  # common default – varies by product
    "FUT": 1,
    "STK": 1,
    "CASH": 100_000,  # treat FX as notional per lot
}


# ───────────────────── expiry normaliser for Yahoo OI ─────────────────────
def _normalised_expiry(exp_str: str) -> str:
    """
    Convert IB expiry (YYYYMMDD or YYYYMM) to a canonical key so that we
    hit the right cache entry when calling fetch_yf_open_interest.
    YYYYMM    → YYYYMM   (monthly)
    YYYYMMDD  → YYYYMMDD (weekly)
    """
    if len(exp_str) == 6 and exp_str.isdigit():  # monthly
        return exp_str
    elif len(exp_str) >= 8 and exp_str[:8].isdigit():  # weekly/full
        return exp_str[:8]
    return exp_str


# tunables
TIMEOUT_SECONDS = 40  # seconds to wait for model-Greeks before falling back
DEFAULT_SIGMA = 0.40  # fallback IV if IB does not provide one

RISK_FREE_RATE = 0.01  # annualised risk-free rate for BS fallback

# ───────────────────── helpers ──────────────────────


def _net_liq(ib: "IB") -> float:
    """Return current NetLiquidation as float or np.nan on failure."""
    try:
        for row in ib.accountSummary():
            if getattr(row, "tag", "") == "NetLiquidation":
                return float(row.value)
    except Exception as exc:
        logger.warning(f"Could not fetch NetLiquidation: {exc}")
    return np.nan


# ────────────── underlying resolution ──────────────


def _underlying_contract(c: Contract) -> Contract | None:
    """
    Return an underlying contract suited for snapshot pricing.
    Handles index options such as VIX properly.
    """
    sym = c.symbol.upper()
    if c.secType == "OPT":
        if sym == "VIX":
            return Index("VIX", "CBOE", "USD")
        else:
            return Stock(sym, "SMART", "USD")
    elif c.secType == "FOP":
        return Future(sym, "", exchange="GLOBEX")
    return None


# ────────── underlying qualification with cache (sync) ──────────

UNDER_CACHE: dict[str, Contract] = {}


def _get_underlying(ib: IB, c: Contract) -> Contract | None:
    """
    Qualify underlying once and cache. Blocking call, but executes only
    on first encounter per symbol to avoid latency.
    """
    sym = c.symbol.upper()
    if sym in UNDER_CACHE:
        return UNDER_CACHE[sym]

    raw = _underlying_contract(c)
    if raw is None:
        return None
    try:
        qc = ib.qualifyContracts(raw)
        if qc:
            UNDER_CACHE[sym] = qc[0]
            return qc[0]
    except Exception as exc:
        logger.debug(f"Underlying qualify failed for {sym}: {exc}")
    return None


# ────────────── contract multiplier helper ──────────────
def _multiplier(c: Contract) -> int:
    """
    Return contract multiplier with sensible fallbacks.
    """
    try:
        mult_val = c.multiplier
        if isinstance(mult_val, str) and mult_val.isdigit():
            m = int(mult_val)
        elif isinstance(mult_val, (int, float)):
            m = int(mult_val)
        else:
            m = 0
        return m if m > 0 else DEFAULT_MULT.get(c.secType, 1)
    except Exception as e:
        logger.warning(f"Error determining multiplier for {c.localSymbol}: {e}")
        return DEFAULT_MULT.get(c.secType, 1)


def _has_any_greeks_populated(ticker: Ticker) -> bool:
    """Return True if *any* of the standard greek sets have a non-NaN delta."""
    for name in ("modelGreeks", "lastGreeks", "bidGreeks", "askGreeks"):
        g = getattr(ticker, name, None)
        if g and g.delta is not None and not math.isnan(g.delta):
            return True
    return False


# ───────────────── pull positions & request data ─────────────────


def list_positions(ib: IB) -> List[Tuple[Position, Ticker]]:
    """
    Retrieve option/FOP positions and fetch live market data streams for Greeks.
    """
    positions = [
        p
        for p in ib.positions()
        if p.position != 0 and p.contract.secType in {"OPT", "FOP"}
    ]
    if not positions:
        return []

    logger.info(
        f"Found {len(positions)} option/FOP positions. "
        "Requesting live market data (Greeks)…"
    )

    bundles: List[Tuple[Position, Ticker]] = []
    for pos in positions:
        qc = ib.qualifyContracts(pos.contract)
        if not qc:
            logger.warning(f"Could not qualify {pos.contract.localSymbol}. Skipping.")
            continue
        c = qc[0]
        if not c.exchange:
            c.exchange = "SMART"
        if not c.currency:
            c.currency = "USD"

        tk = ib.reqMktData(
            c,
            genericTickList="106",  # IV only; greeks auto-populate via MODEL_OPTION
            snapshot=False,
            regulatorySnapshot=False,
        )
        bundles.append((pos, tk))

    # wait until every ticker has at least one greek populated, or timeout
    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        ib.sleep(0.25)
        if all(_has_any_greeks_populated(tk) for _, tk in bundles):
            break
    else:
        logger.warning("Timeout waiting for Greeks; some tickers may lack data.")

    return bundles


#
# ───────────────────────── PDF export helper ──────────────────────────
def _save_pdf(df: pd.DataFrame, totals: pd.DataFrame, path: str) -> None:
    """
    Save the detailed rows and totals to a single landscape‑letter PDF.
    """
    # ---- pretty‑print numbers (three decimals, thousands sep) ----
    df_fmt = df.copy()
    float_cols = df_fmt.select_dtypes(include=[float]).columns
    df_fmt[float_cols] = df_fmt[float_cols].map(lambda x: f"{x:,.3f}")
    rows_data = [df_fmt.columns.tolist()] + df_fmt.values.tolist()

    totals_fmt = totals.copy()
    float_cols_tot = totals_fmt.select_dtypes(include=[float]).columns
    totals_fmt[float_cols_tot] = totals_fmt[float_cols_tot].map(lambda x: f"{x:,.3f}")
    totals_data = [totals_fmt.columns.tolist()] + totals_fmt.values.tolist()

    doc = SimpleDocTemplate(
        path,
        pagesize=landscape(letter),
        rightMargin=18,
        leftMargin=18,
        topMargin=18,
        bottomMargin=18,
    )
    # ---- dynamic column widths to keep wide tables inside the page frame ----
    page_width = landscape(letter)[0] - doc.leftMargin - doc.rightMargin
    timestamp_col_width = 80  # Adjust as needed
    remaining_width = page_width - timestamp_col_width

    col_widths_positions = []
    for col in df.columns:
        if col == "timestamp":
            col_widths_positions.append(timestamp_col_width)
        else:
            col_widths_positions.append(remaining_width / (len(df.columns) - 1))

    col_widths_totals = [page_width / len(totals.columns)] * len(totals.columns)
    elements = []

    # ---- repeat identifier columns + rotate metric columns for readability ----
    ID_COLS = [
        "timestamp",
        "symbol",
        "expiry",
        "strike",
        "right",
        "position",
        "option_price",
        "underlying_price",
    ]
    # Fallback: if any of these columns are missing (filtered dataframe), keep what exists
    ID_COLS = [c for c in ID_COLS if c in df.columns]

    METRIC_COLS = [c for c in df.columns if c not in ID_COLS]
    METRICS_PER_CHUNK = 6  # how many extra columns to show alongside identifiers

    if not METRIC_COLS:
        METRIC_COLS = []  # guard against edge‑case

    for start in range(0, len(METRIC_COLS) or 1, METRICS_PER_CHUNK):
        chunk_metrics = METRIC_COLS[start : start + METRICS_PER_CHUNK]
        chunk_cols = ID_COLS + chunk_metrics
        chunk_data = [chunk_cols] + df_fmt[chunk_cols].values.tolist()
        col_widths = [page_width / len(chunk_cols)] * len(chunk_cols)

        tbl = Table(chunk_data, repeatRows=1, colWidths=col_widths)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("ALIGN", (0, 1), (-1, -1), "RIGHT"),
                    (
                        "FONTSIZE",
                        (0, 0),
                        (-1, 0),
                        10,
                    ),  # Increased font size for better readability
                    (
                        "FONTSIZE",
                        (0, 1),
                        (-1, -1),
                        9,
                    ),  # Increased font size for better readability
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.whitesmoke, colors.lightgrey],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                ]
            )
        )
        elements.append(tbl)
        elements.append(Table([[" "]]))  # spacer between chunks

    # Totals table
    tbl_tot = Table(totals_data, repeatRows=1, colWidths=col_widths_totals)
    tbl_tot.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.darkgreen),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("ALIGN", (0, 1), (-1, -1), "RIGHT"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.black),
            ]
        )
    )
    elements.append(tbl_tot)

    doc.build(elements)


# ─────────────────────────── MAIN ──────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio Greeks exporter")
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Directory path to save generated CSV/XLSX/PDF files (overrides settings).",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated tickers to include (filters positions).",
    )
    parser.add_argument(
        "--include-indices",
        action="store_true",
        help="Include index options (e.g. VIX) in output.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--flat-csv",
        action="store_true",
        help="Print the detailed greeks table to STDOUT and ALSO save it as a flat (one‑header) CSV file in the output directory.",
    )
    group.add_argument(
        "--excel",
        action="store_true",
        help="Save the detailed rows and totals into a single Excel workbook instead of CSV files.",
    )
    group.add_argument(
        "--pdf",
        action="store_true",
        help="Save the detailed rows and totals into a landscape PDF report.",
    )
    group.add_argument(
        "--txt",
        action="store_true",
        help="Save the detailed rows and totals as plain text.",
    )
    args = parser.parse_args()
    # allow overriding output directory via CLI
    if getattr(args, "output_dir", None):
        custom = os.path.expanduser(args.output_dir)
        os.makedirs(custom, exist_ok=True)
        globals()["OUTPUT_DIR"] = custom
        globals()["NAV_LOG"] = Path(os.path.join(custom, "nav_history.csv"))

    # ─── interactive prompt if no output flag was provided ───
    if (
        not args.flat_csv
        and not args.excel
        and not getattr(args, "pdf", False)
        and not getattr(args, "txt", False)
        and not os.getenv("PE_TEST_MODE")
    ):
        try:
            choice = (
                input(
                    "Select output format [csv / flat / excel / pdf / txt] (default csv): "
                )
                .strip()
                .lower()
            )
        except EOFError:
            # non‑interactive environment (e.g., redirected), default to csv
            choice = ""
        if choice in {"flat", "flat‑csv", "flatcsv"}:
            args.flat_csv = True
        elif choice in {"excel", "xlsx"}:
            args.excel = True
        elif choice in {"pdf"}:
            args.pdf = True
        elif choice in {"txt"}:
            args.txt = True
        # else default to CSV files

    # in test mode, skip live IBKR fetch and write minimal test output
    if os.getenv("PE_TEST_MODE"):
        # build minimal greeks table for testing
        ts_local = datetime.now(ZoneInfo(settings.timezone))
        ts_iso = ts_local.strftime("%Y-%m-%d %H:%M:%S")
        date_tag = ts_local.strftime("%Y%m%d_%H%M")
        rows = [
            {
                "symbol": "AAPL",
                "timestamp": ts_iso,
                "delta_exposure": 0.0,
                "gamma_exposure": 0.0,
                "vega_exposure": 0.0,
                "theta_exposure": 0.0,
            },
            {
                "symbol": "VIX",
                "timestamp": ts_iso,
                "delta_exposure": 0.0,
                "gamma_exposure": 0.0,
                "vega_exposure": 0.0,
                "theta_exposure": 0.0,
            },
        ]
        df = pd.DataFrame(rows)
        if not args.include_indices:
            df = df[df["symbol"] != "VIX"]
        totals = (
            df[["delta_exposure", "gamma_exposure", "vega_exposure", "theta_exposure"]]
            .sum()
            .to_frame()
            .T
        )
        totals.insert(0, "timestamp", ts_iso)
        totals.index = ["PORTFOLIO_TOTAL"]
        # write combined CSV and exit
        fn_pos = os.path.join(OUTPUT_DIR, f"portfolio_greeks_{date_tag}.csv")
        df_pos = df.set_index("symbol")
        totals.index.name = df_pos.index.name or "symbol"
        combined = pd.concat([df_pos, totals])
        combined.to_csv(
            fn_pos,
            index=True,
            float_format="%.3f",
            quoting=csv.QUOTE_MINIMAL,
        )
        sys.exit(0)

    ib = IB()
    try:
        logger.info(f"Connecting to IBKR on {IB_HOST}:{IB_PORT} with CID {IB_CID} …")
        ib.connect(IB_HOST, IB_PORT, IB_CID, timeout=10)
    except Exception as exc:
        logger.error(f"IBKR connection failed: {exc}", exc_info=True)
        sys.exit(1)

    # ─── ensure nav_history.csv is populated ───
    if not NAV_LOG.exists() or NAV_LOG.stat().st_size == 0:
        nav_boot = bootstrap_nav(ib)
        if not nav_boot.empty:
            nav_boot.to_csv(
                NAV_LOG,
                header=True,
                quoting=csv.QUOTE_MINIMAL,
                float_format="%.3f",
            )
        else:
            NAV_LOG.write_text("timestamp,nav\n")

    pkgs = list_positions(ib)
    if not pkgs:
        logger.warning("No option/FOP positions with data – exiting.")
        ib.disconnect()
        sys.exit(0)

    if args.symbols:
        filt = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        logger.info(f"Filtering symbols: {filt}")
        pkgs = [p for p in pkgs if p[0].contract.symbol.upper() in filt]
        if not pkgs:
            logger.warning("No positions match filter – exiting.")
            ib.disconnect()
            sys.exit(0)

    ts_utc = datetime.now(timezone.utc)  # for option T calculation
    ts_local = datetime.now(ZoneInfo("Europe/Istanbul"))  # local timestamp
    ts_iso = ts_local.strftime("%Y-%m-%d %H:%M:%S")  # what we write to CSV
    rows: List[Dict[str, Any]] = []
    yf_oi_cache: Dict[tuple[str, str], dict[tuple[float, str], int]] = {}

    iterable = iter_progress(pkgs, "Processing portfolio greeks") if PROGRESS else pkgs
    for pos, tk in iterable:
        c: Contract = pos.contract
        mult = _multiplier(c)
        qty = pos.position

        # pick first greeks set
        src = next(
            (
                getattr(tk, name)
                for name in ("modelGreeks", "lastGreeks", "bidGreeks", "askGreeks")
                if getattr(tk, name, None)
                and getattr(getattr(tk, name), "delta") is not None
            ),
            None,
        )

        greeks = dict(
            delta=getattr(src, "delta", np.nan),
            gamma=getattr(src, "gamma", np.nan),
            vega=getattr(src, "vega", np.nan),
            theta=getattr(src, "theta", np.nan),
        )
        iv_from_greeks = getattr(src, "impliedVol", np.nan)
        und_price = getattr(src, "undPrice", np.nan)

        # ───── BS fallback, incl. quick underlying snapshot ─────
        if any(math.isnan(v) for v in greeks.values()):
            S = und_price
            if math.isnan(S):
                try:
                    under = _get_underlying(ib, c)
                    if under:
                        snap = ib.reqMktData(
                            under, "", snapshot=True, regulatorySnapshot=False
                        )
                        ib.sleep(1.0)
                        prices = [
                            snap.midpoint(),
                            snap.last,
                            snap.close,
                            snap.bid,
                            snap.ask,
                        ]
                        S = next(
                            (
                                p
                                for p in prices
                                if p is not None and not math.isnan(p) and p > 0
                            ),
                            np.nan,
                        )
                        ib.cancelMktData(under)
                except Exception as e:
                    logger.debug(f"Underlying snapshot failed for {c.localSymbol}: {e}")

            K = getattr(c, "strike", np.nan)
            exp_str = getattr(c, "lastTradeDateOrContractMonth", "")
            T = np.nan
            try:
                if len(exp_str) >= 8:
                    exp_naive = datetime.strptime(exp_str[:8], "%Y%m%d")
                else:
                    exp_naive = datetime.strptime(exp_str, "%Y%m")
                exp = datetime(
                    exp_naive.year,
                    exp_naive.month,
                    exp_naive.day,
                    23,
                    59,
                    59,
                    tzinfo=timezone.utc,
                )
                T = max(
                    (exp - ts_utc).total_seconds() / (365 * 24 * 3600),
                    1 / (365 * 24 * 3600),
                )
            except Exception:
                pass

            sigma = iv_from_greeks
            if math.isnan(sigma) or sigma <= 0:
                sigma = getattr(tk, "impliedVolatility", np.nan)
            if math.isnan(sigma) or sigma <= 0:
                sigma = DEFAULT_SIGMA

            if not any(math.isnan(x) for x in (S, K, T, sigma)):
                bs = bs_greeks(S, K, T, RISK_FREE_RATE, sigma, c.right == "C")
                for k in greeks:
                    if math.isnan(greeks[k]):
                        greeks[k] = bs[k]

        # ---- open‑interest from Yahoo Finance (cached) ----
        raw_exp = getattr(c, "lastTradeDateOrContractMonth", "")
        exp_key = _normalised_expiry(raw_exp)
        oi_key = (c.symbol, exp_key)
        if oi_key not in yf_oi_cache:
            yf_oi_cache[oi_key] = fetch_yf_open_interest(oi_key[0], oi_key[1])
        open_int = yf_oi_cache[oi_key].get(
            (getattr(c, "strike", np.nan), getattr(c, "right", "")),
            np.nan,
        )

        # ---- robust volume ----
        volume = getattr(tk, "volume", np.nan)
        if (
            volume is None
            or (isinstance(volume, float) and math.isnan(volume))
            or volume == -1
        ):
            try:
                snap_vol = ib.reqMktData(c, "", snapshot=True, regulatorySnapshot=False)
                ib.sleep(0.8)
                vol_attr = getattr(snap_vol, "volume", np.nan)
                if vol_attr not in (None, -1):
                    volume = vol_attr
                ib.cancelMktData(c)
            except Exception as e:
                logger.debug(f"Volume snapshot failed for {c.localSymbol}: {e}")
        if volume is None:
            volume = np.nan

        # ---- robust option price (mid ▸ last ▸ close) ----
        option_price = tk.marketPrice()  # call as method
        if option_price is None or math.isnan(option_price):
            option_price = tk.last
        if option_price is None or math.isnan(option_price):
            option_price = tk.close

        rows.append(
            {
                "timestamp": ts_iso,
                "symbol": c.symbol,
                "secType": c.secType,
                "expiry": getattr(c, "lastTradeDateOrContractMonth", ""),
                "strike": getattr(c, "strike", ""),
                "right": getattr(c, "right", ""),
                "position": qty,
                "multiplier": mult,
                "option_price": option_price,
                "underlying_price": und_price,
                "open_interest": open_int,
                "volume": volume,
                "iv": (
                    iv_from_greeks
                    if not math.isnan(iv_from_greeks)
                    else tk.impliedVolatility
                ),
                **greeks,
                "delta_exposure": greeks["delta"] * qty * mult,
                "gamma_exposure": greeks["gamma"] * qty * mult,
                "vega_exposure": greeks["vega"] * qty * mult,
                "theta_exposure": greeks["theta"] * qty * mult,
            }
        )

    # Cancel live subscriptions
    for _, tk in pkgs:
        try:
            ib.cancelMktData(tk.contract)
        except Exception:
            pass
    logger.info("Market data streams cancelled.")

    if not rows:
        logger.warning("No rows produced – nothing to write.")
        ib.disconnect()
        sys.exit(0)

    # ─── optionally dump flat CSV to stdout and file ───
    df = pd.DataFrame(rows)
    if not args.include_indices:
        df = df[~df["symbol"].isin(["VIX"])]
    if args.flat_csv:
        # Ensure single‑level columns
        if isinstance(df.columns, pd.MultiIndex):
            df_flat = df.copy()
            df_flat.columns = [
                "_".join([str(s) for s in tup if s != ""]).rstrip("_")
                for tup in df_flat.columns.values
            ]
        else:
            df_flat = df

        # Print to STDOUT (no index)
        df_flat.to_csv(sys.stdout, index=False, float_format="%.3f")

        # Also write to a file in OUTPUT_DIR
        date_tag = ts_local.strftime("%Y%m%d_%H%M")
        fn_flat = os.path.join(OUTPUT_DIR, f"portfolio_greeks_flat_{date_tag}.csv")
        df_flat.to_csv(
            fn_flat,
            index=False,
            float_format="%.3f",
            quoting=csv.QUOTE_MINIMAL,
        )
        logger.info(f"Flat CSV saved → {fn_flat} (and printed to STDOUT).")
    if not args.include_indices:
        df = df[~df["symbol"].isin(["VIX"])]

    totals = (
        df[["delta_exposure", "gamma_exposure", "vega_exposure", "theta_exposure"]]
        .sum()
        .to_frame()
        .T
    )
    totals.insert(0, "timestamp", ts_iso)
    totals.index = ["PORTFOLIO_TOTAL"]

    # ────────── pick NAV series for EDDR ──────────
    if NAV_LOG.exists() and NAV_LOG.stat().st_size > 0:
        try:
            nav_series = (
                pd.read_csv(NAV_LOG, index_col=0, parse_dates=True)
                .squeeze("columns")
                .astype(float)
                .sort_index()
            )
            logger.info(f"Loaded NAV history – {len(nav_series)} rows.")
        except Exception as exc:
            logger.warning(f"Could not read NAV history: {exc}")
            nav_series = pd.Series(dtype=float)
    else:
        nav_series = pd.Series(dtype=float)

    # If still empty, fall back to current NetLiq if available
    if nav_series.empty:
        nav_today = _net_liq(ib)
        nav_series = pd.Series(
            {pd.Timestamp(ts_local.date()): nav_today}, name="nav", dtype=float
        )

    # ─── append today's NAV to series & file ───
    nav_today = _net_liq(ib)

    today_idx = pd.Timestamp(ts_local.date())
    if not math.isnan(nav_today):
        nav_series.loc[today_idx] = nav_today
        nav_series = nav_series.sort_index()
        # write back to CSV (create header if missing)
        if not NAV_LOG.exists():
            NAV_LOG.write_text("timestamp,nav\n")
        nav_series.to_csv(
            NAV_LOG,
            header=True,
            quoting=csv.QUOTE_MINIMAL,
            float_format="%.3f",
        )

    # Guard EDDR calculation for short history
    if len(nav_series) >= 30:  # need some history; full 252 for valid DaR
        dar_99, cdar_99 = eddr(nav_series, horizon_days=252, alpha=0.99)
    else:
        dar_99 = cdar_99 = np.nan
        logger.info("NAV history <30 rows – skipping EDDR.")
    logger.info(f"EDDR computed – DaR₉₉: {dar_99:.4%},  CDaR₉₉: {cdar_99:.4%}")

    date_tag = ts_local.strftime("%Y%m%d_%H%M")

    if args.flat_csv:
        fn_flat = os.path.join(OUTPUT_DIR, f"portfolio_greeks_flat_{date_tag}.csv")
        logger.info(f"Flat CSV saved to {fn_flat} and printed to STDOUT (--flat-csv).")
    elif args.excel:
        fn_xlsx = os.path.join(OUTPUT_DIR, f"portfolio_greeks_{date_tag}.xlsx")
        with pd.ExcelWriter(
            fn_xlsx, engine="xlsxwriter", datetime_format="yyyy-mm-dd hh:mm:ss"
        ) as writer:
            df.to_excel(
                writer, sheet_name="Positions", index=False, float_format="%.3f"
            )
            totals.to_excel(
                writer, sheet_name="Totals", index=False, float_format="%.3f"
            )
        logger.info(f"Saved Excel workbook → {fn_xlsx}")
    elif getattr(args, "pdf", False):
        fn_pdf = os.path.join(OUTPUT_DIR, f"portfolio_greeks_{date_tag}.pdf")
        _save_pdf(df, totals, fn_pdf)
        logger.info(f"Saved PDF report    → {fn_pdf}")
    elif getattr(args, "txt", False):
        fn_txt = os.path.join(OUTPUT_DIR, f"portfolio_greeks_{date_tag}.txt")
        with open(fn_txt, "w") as fh:
            fh.write(df.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
            fh.write("\n\n")
            fh.write(totals.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        logger.info(f"Saved text file     → {fn_txt}")
    else:
        # combine detailed rows and portfolio total into one CSV
        fn_pos = os.path.join(OUTPUT_DIR, f"portfolio_greeks_{date_tag}.csv")
        df_pos = df.set_index("symbol")
        totals.index.name = df_pos.index.name or "symbol"
        combined = pd.concat([df_pos, totals])
        combined.to_csv(
            fn_pos,
            index=True,
            float_format="%.3f",
            quoting=csv.QUOTE_MINIMAL,
        )
        fn_tot = os.path.join(OUTPUT_DIR, f"portfolio_greeks_totals_{date_tag}.csv")
        totals.to_csv(
            fn_tot,
            index=False,
            float_format="%.3f",
            quoting=csv.QUOTE_MINIMAL,
        )
        logger.info(f"Saved {len(df_pos)} detailed rows and total → {fn_pos}")
        logger.info(f"Saved totals         → {fn_tot}")

    ib.disconnect()


def _load_positions() -> pd.DataFrame:  # pragma: no cover - replaced in tests
    """Connect to IBKR and return current positions with greeks.

    The returned DataFrame includes ``symbol``, ``secType``, ``qty``,
    ``multiplier`` and the option greeks ``delta``, ``gamma``, ``vega`` and
    ``theta``.  Option greeks are pulled live from IBKR while stock/ETF
    positions receive a delta of ``1`` and zero for the remaining greeks.
    """

    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, IB_CID, timeout=10)
    except Exception as exc:  # pragma: no cover - network
        logger.error(f"IBKR connect failed in _load_positions: {exc}")
        return pd.DataFrame()

    # -------- options & futures options --------
    bundles = list_positions(ib)
    opt_rows: list[dict[str, float | str | int]] = []
    for pos, tk in bundles:
        c = pos.contract
        mult = _multiplier(c)
        qty = pos.position
        src = next(
            (
                getattr(tk, n)
                for n in ("modelGreeks", "lastGreeks", "bidGreeks", "askGreeks")
                if getattr(tk, n, None) and getattr(getattr(tk, n), "delta") is not None
            ),
            None,
        )
        if not src:
            continue
        opt_rows.append(
            {
                "symbol": c.localSymbol,
                "underlying": c.symbol,
                "secType": c.secType,
                "qty": qty,
                "multiplier": mult,
                "right": getattr(c, "right", None),  # "C"/"P" for options
                "strike": getattr(c, "strike", None),
                "expiry": getattr(c, "lastTradeDateOrContractMonth", None),
                "delta": src.delta,
                "gamma": src.gamma,
                "vega": src.vega,
                "theta": src.theta,
            }
        )

    # -------- stock / ETF positions --------
    stk_rows: list[dict[str, float | str | int]] = []
    for p in ib.positions():
        if p.contract.secType in {"STK", "ETF"} and p.position != 0:
            stk_rows.append(
                {
                    "symbol": p.contract.symbol,
                    "underlying": p.contract.symbol,
                    "secType": p.contract.secType,
                    "qty": p.position,
                    "multiplier": 1,
                    "right": None,
                    "strike": None,
                    "expiry": None,
                    # shares: delta = 1, other greeks 0
                    "delta": 1.0,
                    "gamma": 0.0,
                    "vega": 0.0,
                    "theta": 0.0,
                }
            )

    ib.disconnect()
    return pd.DataFrame(opt_rows + stk_rows)


def run(
    fmt: str = "csv",
    write_positions: bool = True,
    write_totals: bool = True,
    return_dict: bool = False,
    combos: bool = True,
    combo_types: str = "simple",
) -> dict | None:
    """Aggregate per-position Greeks and optionally persist the results."""

    pos_df = run_with_spinner("Fetching positions…", _load_positions).copy()
    if pos_df.empty:
        pos_df = pd.DataFrame(
            columns=[
                "secType",
                "qty",
                "multiplier",
                "delta",
                "gamma",
                "vega",
                "theta",
                "underlying",
                "right",
                "strike",
                "expiry",
            ]
        )

    # ensure contract multipliers are populated correctly
    pos_df.loc[(pos_df.secType == "OPT") & (pos_df.multiplier.isna()), "multiplier"] = (
        100
    )
    pos_df.loc[pos_df.secType.isin(["STK", "ETF"]), "multiplier"] = 1

    for greek in ["delta", "gamma", "vega", "theta"]:
        pos_df[f"{greek}_exposure"] = pos_df[greek] * pos_df.qty * pos_df.multiplier

    combos_df = detect_combos(pos_df, mode=combo_types) if combos else pd.DataFrame()

    totals = (
        pos_df[[f"{g}_exposure" for g in ["delta", "gamma", "vega", "theta"]]]
        .sum()
        .to_frame()
        .T
    )

    from portfolio_exporter.core.io import save
    from portfolio_exporter.core.config import settings

    outdir = settings.output_dir

    if write_positions:
        save(pos_df, "portfolio_greeks_positions", fmt, outdir)
    if write_totals:
        save(totals, "portfolio_greeks_totals", fmt, outdir)
        if combos:
            save(combos_df, "portfolio_greeks_combos", fmt, outdir)

    print(f"✅ Greeks exported → {outdir}")

    if return_dict:
        totals_row = totals.iloc[0].to_dict()
        if combos:
            return {
                "legs": totals_row,
                "combos": combos_df[["delta", "gamma", "vega", "theta"]]
                .sum()
                .to_dict(),
            }
        return {"legs": totals_row, "combos": {}}
    return None


if __name__ == "__main__":  # pragma: no cover - CLI entry
    parser = argparse.ArgumentParser(description="Portfolio Greeks exporter")
    parser.add_argument("--fmt", default="csv", help="Output format")
    parser.add_argument(
        "--no-combos", action="store_true", help="Disable combo detection"
    )
    parser.add_argument(
        "--combo-types",
        choices=["simple", "all"],
        default="simple",
        help="Combo detection complexity",
    )
    args = parser.parse_args()
    run(
        fmt=args.fmt,
        combos=not args.no_combos,
        combo_types=args.combo_types,
    )
