#!/usr/bin/env python3
from __future__ import annotations

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
import hashlib
try:
    import requests
except Exception:  # pragma: no cover - optional dependency
    requests = None  # type: ignore
import calendar
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Tuple, Optional
from pathlib import Path
try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
except Exception:  # pragma: no cover - optional dependency
    Console = None  # type: ignore
    Table = None  # type: ignore
    box = None  # type: ignore
import sqlite3
import pandas as pd

# Prefer in-package BS greeks; fall back to legacy utils in dev trees
try:
    from portfolio_exporter.core.greeks import bs_greeks  # type: ignore
except Exception:  # pragma: no cover - optional fallback for local dev
    from utils.bs import bs_greeks  # type: ignore
try:
    from legacy.option_chain_snapshot import fetch_yf_open_interest
except Exception:  # pragma: no cover - optional
    def fetch_yf_open_interest(*args, **kwargs):  # type: ignore
        return {}
try:
    from portfolio_exporter.core import ui as core_ui
    run_with_spinner = core_ui.run_with_spinner
except Exception:  # pragma: no cover - fallback
    def run_with_spinner(msg, func, *args, **kwargs):
        return func(*args, **kwargs)
from portfolio_exporter.core import combo as combo_core
from portfolio_exporter.core import io as io_core
from portfolio_exporter.core import config as config_core
from portfolio_exporter.core import cli as cli_helpers
from portfolio_exporter.core import json as json_helpers
from portfolio_exporter.core.runlog import RunLog

import numpy as np

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

try:
    from ib_insync import Future, IB, Index, Option, Position, Stock, Ticker, util
    from ib_insync.contract import Contract
except Exception:  # pragma: no cover - optional dependency
    Future = IB = Index = Option = Position = Stock = Ticker = util = Contract = None  # type: ignore

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
# Alias for consistency with other modules/snippets
log = logger
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

NAV_LOG = Path(os.path.join(OUTPUT_DIR, "nav_history.csv"))

try:
    from portfolio_exporter.core.ib_config import HOST as IB_HOST, PORT as IB_PORT, client_id as _cid
except Exception:  # pragma: no cover - optional fallback
    IB_HOST = "127.0.0.1"  # type: ignore
    IB_PORT = 7497  # type: ignore

    def _cid(name: str, default: int = 0) -> int:  # type: ignore
        return default
IB_CID = _cid("portfolio_greeks", default=11)  # separate clientId from snapshots

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
    raw_positions = [p for p in ib.positions() if p.position != 0]

    # Expand IB "BAG" combo positions into per-leg pseudo-positions so we can
    # fetch Greeks for each option leg. Some accounts only show combos as BAGs
    # without separate option legs; previously these were silently skipped.
    positions: list[Position] = []
    for p in raw_positions:
        try:
            st = getattr(p.contract, "secType", "")
        except Exception:
            st = ""
        if st in {"OPT", "FOP"}:
            positions.append(p)
            continue
        if st == "BAG":
            try:
                legs = getattr(p.contract, "comboLegs", None) or []
                if not legs:
                    continue
                # For each leg, qualify by conId and synthesize a Position-like object
                for leg in legs:
                    try:
                        # Qualify the leg contract by conId to obtain full details
                        c = Contract()
                        c.conId = int(getattr(leg, "conId"))
                        cds = ib.reqContractDetails(c)
                        lc = cds[0].contract if cds else None
                        if lc is None:
                            continue
                        # Compute effective leg quantity (respect leg action/buy/sell and ratio)
                        ratio = int(getattr(leg, "ratio", 1) or 1)
                        action = str(getattr(leg, "action", "")).upper()
                        eff_qty = int(p.position) * ratio
                        if action == "SELL":
                            eff_qty *= -1

                        # Build a minimal Position-like object with required attributes
                        class _PosLike:
                            def __init__(self, contract, position):
                                self.contract = contract
                                self.position = position

                        positions.append(_PosLike(lc, eff_qty))
                    except Exception:
                        # Skip legs we cannot qualify
                        continue
            except Exception:
                # Defensive: if anything goes wrong, just skip the BAG
                continue

    # Keep only option-like instruments after expansion
    positions = [p for p in positions if getattr(p.contract, "secType", "") in {"OPT", "FOP"}]
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
    # Build avg cost lookup by conId for P&L calculations
    avg_cost_map: dict[int, float] = {}
    try:
        for p in ib.positions():
            try:
                cid = int(getattr(p.contract, "conId", 0))
                if cid:
                    avg_cost_map[cid] = float(getattr(p, "avgCost", float("nan")))
            except Exception:
                continue
    except Exception:
        pass

    opt_rows: list[dict[str, float | str | int]] = []
    for pos, tk in bundles:
        c = pos.contract
        mult = _multiplier(c)
        qty = pos.position
        # Try to pick a greeks source if available; otherwise leave NaN and let downstream handle
        src = next(
            (
                getattr(tk, n)
                for n in ("modelGreeks", "lastGreeks", "bidGreeks", "askGreeks")
                if getattr(tk, n, None) and getattr(getattr(tk, n), "delta") is not None
            ),
            None,
        )
        # robust option price (mid ▸ last ▸ close)
        option_price = None
        try:
            option_price = tk.marketPrice()  # call as method
        except Exception:
            option_price = None
        if option_price is None or (isinstance(option_price, float) and math.isnan(option_price)):
            option_price = getattr(tk, "last", None)
        if option_price is None or (isinstance(option_price, float) and math.isnan(option_price)):
            option_price = getattr(tk, "close", None)
        try:
            conid_val = int(getattr(c, "conId", 0))
        except Exception:
            conid_val = 0
        avg_cost_raw = avg_cost_map.get(conid_val, float("nan"))
        # Normalize avg cost to per-unit for options/FOP where needed.
        # Some IB endpoints return avgCost per contract (price * multiplier), others per unit.
        # Heuristic: if avg_cost is much larger than the current mark price and multiplier>1, treat it as per-contract and divide.
        per_unit_cost = float("nan")
        try:
            ac = float(avg_cost_raw)
            mp = float(option_price) if option_price is not None else float("nan")
            if getattr(c, "secType", "") in {"OPT", "FOP"} and mult and float(mult) > 1:
                if (not math.isnan(mp) and ac > mp * 10) or ac > 50:
                    per_unit_cost = ac / float(mult)
                else:
                    per_unit_cost = ac
            else:
                per_unit_cost = ac
        except Exception:
            per_unit_cost = float("nan")
        try:
            # Unrealized P&L per leg: (mark_per_unit − per_unit_cost) × qty × multiplier
            pnl_leg = (float(option_price) - per_unit_cost) * float(qty) * float(mult)
        except Exception:
            pnl_leg = float("nan")

        opt_rows.append(
            {
                "symbol": c.localSymbol,
                "underlying": c.symbol,
                "secType": c.secType,
                "conId": getattr(c, "conId", None),
                "qty": qty,
                "multiplier": mult,
                "right": getattr(c, "right", None),  # "C"/"P" for options
                "strike": getattr(c, "strike", None),
                "expiry": getattr(c, "lastTradeDateOrContractMonth", None),
                "delta": getattr(src, "delta", float("nan")),
                "gamma": getattr(src, "gamma", float("nan")),
                "vega": getattr(src, "vega", float("nan")),
                "theta": getattr(src, "theta", float("nan")),
                "price": option_price if option_price is not None else float("nan"),
                "avg_cost": avg_cost_raw,
                "avg_cost_unit": per_unit_cost,
                "pnl_leg": pnl_leg,
            }
        )

    # -------- stock / ETF positions --------
    stk_rows: list[dict[str, float | str | int]] = []
    for p in ib.positions():
        if p.contract.secType in {"STK", "ETF"} and p.position != 0:
            # best-effort price snapshot is not fetched here; leave price NaN
            ac = float(getattr(p, "avgCost", float("nan")))
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
                    "price": float("nan"),
                    "avg_cost": ac,
                    "avg_cost_unit": ac,
                    "pnl_leg": float("nan"),
                }
            )

    ib.disconnect()
    return pd.DataFrame(opt_rows + stk_rows)


def _load_db_legs_map() -> dict[str, list[dict[str, object]]]:
    """
    Build a mapping of combo legs from the SQLite DB.

    Purpose
    - Return a dictionary keyed by `combo_id` with a list of per‑leg detail dicts:
      { combo_id: [{"conid": int|None, "right": 'C'/'P'/'' , "strike": float|None, "secType": str|None}, ...] }.

    Data sources
    - Reads from either `combo_legs` or `legs` table if present.

    Supported columns
    - Accepts any available subset of: `combo_id`, `conid`/`conId`, `right`, `strike`, `secType`/`sec_type`.

    Normalization
    - Coerces `conid` to int when possible; `strike` to float; `right` to 'C'/'P' or empty string for non‑options; keeps `secType` as provided.

    Behavior
    - Returns an empty mapping if the DB file or legs table does not exist; tolerates missing fields by including what is available without failing.
    """
    try:
        db_path = os.environ.get("PE_DB_PATH") or (Path(settings.output_dir) / "combos.db")
        if not Path(db_path).exists():
            return {}
        out: dict[str, list[dict[str, object]]] = {}
        with sqlite3.connect(db_path) as con:
            # Prefer combo_legs; fallback to legs
            table = None
            for t in ("combo_legs", "legs"):
                try:
                    cols = [c[1] for c in con.execute(f"PRAGMA table_info({t});")]
                except Exception:
                    cols = []
                if cols:
                    table = t
                    break
            if not table:
                return {}

            cols = [c[1] for c in con.execute(f"PRAGMA table_info({table});")]
            # Build SELECT with available columns (support 'conId' alias)
            base_candidates = ["combo_id", "conid", "conId", "right", "strike", "secType", "sec_type"]
            sel_cols = [c for c in base_candidates if c in cols]
            if "combo_id" not in sel_cols:
                return {}
            q = f"SELECT {', '.join(sel_cols)} FROM {table}"
            df = pd.read_sql_query(q, con)
            if df.empty:
                return {}

            # Normalise columns
            if "conId" in df.columns and "conid" not in df.columns:
                df = df.rename(columns={"conId": "conid"})
            if "sec_type" in df.columns and "secType" not in df.columns:
                df = df.rename(columns={"sec_type": "secType"})
            for c in ["conid", "strike"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            if "right" in df.columns:
                df["right"] = df["right"].astype(str).str.upper().replace({"NAN": ""})
                df.loc[~df["right"].isin(["C", "P"]) , "right"] = ""
            if "secType" in df.columns:
                df["secType"] = df["secType"].astype(str)

            for combo_id, group in df.groupby("combo_id"):
                legs: list[dict[str, object]] = []
                for _, r in group.iterrows():
                    legs.append(
                        {
                            "conid": int(r["conid"]) if not pd.isna(r.get("conid")) else None,
                            "right": str(r.get("right")) if "right" in r else "",
                            "strike": float(r.get("strike")) if "strike" in r and not pd.isna(r.get("strike")) else None,
                            "secType": str(r.get("secType")) if "secType" in r else None,
                        }
                    )
                out[str(combo_id)] = legs
        return out
    except Exception:
        return {}


def _load_db_combos_or_none():
    """
    Load combos from the `combos` table in the SQLite DB.

    Purpose
    - Retrieve stored combos and attach legs information for downstream enrichment.

    Behavior
    - Pulls base columns from `combos` and, when present, also reads embedded JSON legs from `legs` or `combo_legs` columns on the same table.
    - Calls `_load_db_legs_map()` to attach two helper columns when available:
      • `legs`: a list of conIds (missing items preserved as `None`).
      • `__db_legs_detail`: list of dicts with leg details (right/strike/secType).
    - If a combo has no direct legs but `parent_combo_id` exists and parent legs are available, uses the parent’s legs as a fallback.
    - Keeps `combo_id` for downstream processing. Helper columns are subsequently dropped before writing the final CSV to disk.
    """
    import os, sqlite3
    import pandas as pd
    from pathlib import Path
    from portfolio_exporter.core.config import settings

    db = os.environ.get("PE_DB_PATH") or (Path(settings.output_dir) / "combos.db")
    if not Path(db).exists():
        return None
    try:
        with sqlite3.connect(db) as con:
            cols = [c[1] for c in con.execute("PRAGMA table_info(combos);")]
            want = [
                c
                for c in [
                    "combo_id",
                    "underlying",
                    "expiry",
                    "type",
                    "width",
                    "credit_debit",
                    "parent_combo_id",
                    "closed_date",
                    "structure",
                ]
                if c in cols
            ]
            if not want:
                return None
            # Optionally pull embedded legs columns if they exist on combos
            extra = []
            for c in ("legs", "combo_legs"):
                if c in cols:
                    extra.append(c)
            sel_cols = want + extra
            df = pd.read_sql_query(f"SELECT {', '.join(sel_cols)} FROM combos", con)
            if "combo_legs" in df.columns and "legs" not in df.columns:
                df["legs"] = df["combo_legs"]
            # Attach legs and detailed legs from DB if present
            legs_map = _load_db_legs_map()
            if legs_map:
                # Build columns without a heavy merge to avoid type coercion
                legs_col: list[object] = []
                legs_detail_col: list[object] = []
                for _, r in df.iterrows():
                    cid = str(r.get("combo_id"))
                    pid = str(r.get("parent_combo_id")) if "parent_combo_id" in r and pd.notna(r.get("parent_combo_id")) else None
                    items = legs_map.get(cid, [])
                    if not items and pid:
                        items = legs_map.get(pid, [])
                    legs_detail_col.append(items)
                    # Build 'legs' as list of conids where present; if missing, append None
                    mix: list[int | None] = []
                    for it in items:
                        conid = it.get("conid")
                        if isinstance(conid, (int,)):
                            mix.append(int(conid))
                        else:
                            mix.append(None)
                    legs_col.append(mix)
                df["legs"] = legs_col
                df["__db_legs_detail"] = legs_detail_col
        if df.empty:
            return None
        return df
    except Exception:
        return None


# Known multi-leg structures
KNOWN_MULTI = {"vertical", "iron condor", "butterfly", "calendar"}


def _choose_combos_df(
    source: str, positions_df: pd.DataFrame, combo_types: str
) -> tuple[pd.DataFrame, str]:
    """Resolve combo DataFrame from desired *source* and filter to true combos.

    Preference in "auto" mode: live → engine → db.
    """

    resolved = source
    df_raw: pd.DataFrame | None = None

    # --- Live detection first (preferred) --------------------------------
    if source in {"auto", "live"}:
        try:
            live_df = combo_core.detect_from_positions(positions_df)
            if live_df is not None and not live_df.empty:
                df_raw = live_df
                resolved = "live"
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Live combo detection failed: %s", e)

    # --- Engine fallback --------------------------------------------------
    if (df_raw is None or df_raw.empty) and source in {"auto", "engine"}:
        try:
            try:
                engine_df = combo_core.detect_combos(positions_df, mode=combo_types)
            except TypeError:  # backward compat
                engine_df = combo_core.detect_combos(positions_df)
            if engine_df is not None and not engine_df.empty:
                df_raw = engine_df
                resolved = "engine"
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Engine combo detection failed: %s", e)

    # --- DB as last resort (explicit or auto) ----------------------------
    if (df_raw is None or df_raw.empty) and source in {"auto", "db"}:
        db_df = _load_db_combos_or_none()
        informative = False
        if db_df is not None:
            if "structure" in db_df.columns:
                lc = db_df["structure"].astype(str).str.lower()
            elif "type" in db_df.columns:
                lc = db_df["type"].astype(str).str.lower()
            else:
                lc = pd.Series(dtype=str)
            informative = lc.isin(KNOWN_MULTI).any()
            if not informative and "width" in db_df.columns:
                informative = (
                    pd.to_numeric(db_df["width"], errors="coerce").fillna(0) > 0
                ).any()
            if not informative and "legs" in db_df.columns:
                informative = (
                    db_df["legs"]
                    .apply(lambda v: isinstance(v, (list, tuple)) and len(v) >= 2)
                    .any()
                )
        if informative and db_df is not None:
            df_raw = db_df
            resolved = "db"
        elif source == "db":
            df_raw = pd.DataFrame()
            resolved = "db"

    combos_df = _normalize_combos_columns(df_raw)
    try:
        log.info("Combos raw columns: %s", list(combos_df.columns))
    except Exception:
        pass
    raw_count = 0 if df_raw is None else len(df_raw)
    combos_df = _filter_true_combos(combos_df)

    # One-line summary of live detection results
    try:
        s = combos_df.get("structure", pd.Series(dtype=str)).astype(str).str.lower().str.strip()
        v_cnt = int((s == "vertical").sum())
        ic_cnt = int((s == "iron condor").sum())
        bf_cnt = int((s == "butterfly").sum())
        cal_cnt = int((s == "calendar").sum())
        total = int(len(combos_df))
        log.info(
            "Live combos detected: %s vertical, %s condor, %s butterfly, %s calendar; total=%s",
            v_cnt,
            ic_cnt,
            bf_cnt,
            cal_cnt,
            total,
        )
    except Exception:
        pass

    log.info(
        "Combos chosen: %d (source=%s, raw=%d)",
        len(combos_df),
        resolved,
        raw_count,
    )

    if os.getenv("PE_DEBUG_COMBOS") == "1":
        try:
            dbg = df_raw if df_raw is not None else pd.DataFrame()
            io_core.save(dbg, "combos_raw_debug", "csv", config_core.settings.output_dir)
        except Exception:
            pass

    return combos_df, resolved


def _filter_true_combos(df: pd.DataFrame) -> pd.DataFrame:
    raw = 0 if df is None else len(df)
    if raw == 0:
        log.info("Combos filter: raw=0 kept=0 (nothing to do)")
        return df

    s_norm = df.get("structure", pd.Series(index=df.index, dtype="object")).astype(str).str.lower().str.strip()
    t_norm = df.get("type", pd.Series(index=df.index, dtype="object")).astype(str).str.lower().str.strip()
    legs = df.get("legs", pd.Series(index=df.index, dtype="object"))
    legs_n = df.get("legs_n", pd.Series(index=df.index, dtype="Int64"))

    known_multi = {"vertical", "iron condor", "butterfly", "calendar", "diagonal", "diag", "strangle", "straddle", "ratio"}
    has_known = s_norm.isin(known_multi) | t_norm.isin(known_multi)

    non_empty = lambda s: s.notna() & (s != "") & (s != "nan")
    has_non_single = (non_empty(s_norm) & ~s_norm.eq("single")) | (non_empty(t_norm) & ~t_norm.eq("single"))
    def _has2(v):
        if isinstance(v, (list, tuple)):
            return len(v) >= 2
        try:
            x = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
            return bool(pd.notna(x) and x >= 2)
        except Exception:
            return False

    has_legs2 = legs.apply(_has2)
    if not legs_n.isna().all():
        has_legs2 = has_legs2 | legs_n.fillna(0).ge(2)

    keep = has_known | has_legs2 | has_non_single

    kept_df = df[keep].copy()
    kept = len(kept_df)

    # Debug logging for diagnostics
    try:
        s_vals = s_norm[non_empty(s_norm)].value_counts().head(10).to_dict()
        t_vals = t_norm[non_empty(t_norm)].value_counts().head(10).to_dict()
        log.info(
            "Combos filter: raw=%d kept=%d (known=%d legs2=%d) struct_top=%s type_top=%s",
            raw,
            kept,
            int(has_known.sum()),
            int(has_legs2.fillna(False).sum()),
            s_vals,
            t_vals,
        )
    except Exception:
        log.info(
            "Combos filter: raw=%d kept=%d (known=%d legs2=%d)",
            raw,
            kept,
            int(has_known.sum()),
            int(has_legs2.fillna(False).sum()),
        )

    return kept_df


def _normalize_combos_columns(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "underlying",
                "expiry",
                "structure",
                "structure_label",
                "type",
                "legs",
                "legs_n",
                "width",
                "credit_debit",
                "parent_combo_id",
                "closed_date",
            ]
        )

    out = df.copy()

    # carry optional user-facing label if provided
    if "structure_label" not in out.columns:
        out["structure_label"] = ""
    out["structure_label"] = out["structure_label"].fillna("").astype(str)

    for col in ["structure", "type"]:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("").astype(str)

    if "legs" not in out.columns:
        # Ensure nullable integer dtype; do not force default 1
        out["legs"] = pd.Series([pd.NA] * len(out), dtype="Int64")
    if "width" not in out.columns:
        out["width"] = np.nan
    if "credit_debit" not in out.columns:
        out["credit_debit"] = np.nan
    for col in ["parent_combo_id", "closed_date"]:
        if col not in out.columns:
            out[col] = np.nan
    if "underlying" not in out.columns:
        out["underlying"] = ""

    if "expiry" not in out.columns:
        out["expiry"] = ""
    else:
        def _norm_exp(x: Any) -> str:
            s = str(x).strip()
            if not s:
                return ""
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
                try:
                    return (
                        pd.to_datetime(s, format=fmt, errors="raise")
                        .date()
                        .isoformat()
                    )
                except Exception:
                    pass
            try:
                return pd.to_datetime(s, errors="coerce").date().isoformat()
            except Exception:
                return s

        out["expiry"] = out["expiry"].apply(_norm_exp)

    # New: standardize structure/type strings (lower, stripped) without overriding non-empty values
    for col in ("structure", "type"):
        if col in out.columns:
            out[col] = out[col].astype(str).str.strip()

    # ---- Fill structure/type from alternates & normalize ----
    if out["structure"].replace("", np.nan).isna().all():
        for alt in ["strategy", "kind", "combo_type", "structure_name"]:
            if alt in out.columns and not out[alt].replace("", np.nan).isna().all():
                out["structure"] = out[alt].astype(str)
                break

    if out["type"].replace("", np.nan).isna().all():
        # mirror structure if type missing
        if out["structure"].notna().any():
            mask = out["type"].isin(["", "nan"]) | out["type"].isna()
            out.loc[mask, "type"] = out["structure"].astype(str)

    out["structure"] = out["structure"].astype(str).str.strip()
    out["type"] = out["type"].astype(str).str.strip()

    # ---- Derive numeric legs_n (keep original 'legs' as-is) ----
    def _lenish(v):
        if isinstance(v, (list, tuple)):
            return len(v)
        if isinstance(v, str) and v.startswith("[") and v.endswith("]"):
            try:
                import ast
                parsed = ast.literal_eval(v)
                return len(parsed) if isinstance(parsed, (list, tuple)) else np.nan
            except Exception:
                return np.nan
        try:
            x = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
            return int(x) if pd.notna(x) else np.nan
        except Exception:
            return np.nan

    if "legs" in out.columns:
        out["legs_n"] = out["legs"].apply(_lenish).astype("Int64")
    else:
        out["legs_n"] = pd.Series([pd.NA] * len(out), dtype="Int64")

    # Preserve helper/internal columns if present
    extra_cols: list[str] = []
    for c in ("combo_id", "__db_legs_detail"):
        if c in out.columns:
            extra_cols.append(c)

    return out[
        [
            "underlying",
            "expiry",
            "structure",
            "structure_label",
            "type",
            "legs",
            "legs_n",
            "width",
            "credit_debit",
            "parent_combo_id",
            "closed_date",
        ]
        + extra_cols
    ]


def _enrich_combo_strikes(
    combos_df: pd.DataFrame, positions_df: pd.DataFrame | None
) -> pd.DataFrame:
    """
    Populate strike details and leg counts for all combos.

    Purpose
    - Ensure the following columns are present and populated when possible for every combo row:
      • `strikes` (all strikes), `call_strikes`, `put_strikes`
      • `call_count`, `put_count`, `has_stock_leg`

    Enrichment order
    1) Prefer `positions_df` mapping by conId → (right/strike/secType) when provided.
    2) Fallback to DB legs via `__db_legs_detail` for legs that positions cannot resolve.

    Leg sources supported
    - Separate `legs`/`combo_legs` table rows (via `_load_db_legs_map`).
    - Embedded JSON legs (or `combo_legs`) column on the `combos` table.
    - Parent combo legs when a child `combo_id` lacks its own legs.

    Debug mode
    - When `PE_DEBUG_COMBOS=1`, writes `combos_enriched_debug.csv` including a `__strike_source` hint per row ('pos' or 'db').

    Data normalization
    - Prior to saving the final CSV, the `legs` column is normalized to a JSON list and `legs_n` matches its length.

    Edge cases
    - If neither positions nor DB legs contain strike/right information, the strike columns remain empty and counts may be zero for that combo.
    """
    if combos_df is None or combos_df.empty:
        # Nothing to do – still ensure the columns exist for downstream code
        df = combos_df.copy() if isinstance(combos_df, pd.DataFrame) else pd.DataFrame()
        for col in [
            "strikes",
            "call_strikes",
            "put_strikes",
        ]:
            if col not in df.columns:
                df[col] = ""
        for col in ["call_count", "put_count"]:
            if col not in df.columns:
                df[col] = 0
        if "has_stock_leg" not in df.columns:
            df["has_stock_leg"] = False
        try:
            total_calls = int(df.get("call_count", pd.Series(dtype=int)).sum()) if not df.empty else 0
            total_puts = int(df.get("put_count", pd.Series(dtype=int)).sum()) if not df.empty else 0
            logger.info(
                "Combos enrichment: %d rows (calls=%d puts=%d with strikes)",
                len(df),
                total_calls,
                total_puts,
            )
        except Exception:
            pass
        return df

    df = combos_df.copy()

    # Initialize output columns with defaults so downstream consumers always have them
    df["strikes"] = ""
    df["call_strikes"] = ""
    df["put_strikes"] = ""
    df["call_count"] = 0
    df["put_count"] = 0
    df["has_stock_leg"] = False
    # Helper column to indicate enrichment source for debug CSV
    df["__strike_source"] = ""

    # Track DB fallback rows for logging
    db_fallback_rows = 0

    # Build lookup: conId -> {right, strike, secType}
    if positions_df is None or (isinstance(positions_df, pd.DataFrame) and positions_df.empty):
        pos_lookup = pd.DataFrame(columns=["right", "strike", "secType"]).set_index(
            pd.Index([], name="conid")
        )
    else:
        try:
            p = positions_df.copy()
            if "conId" in p.columns and "conid" not in p.columns:
                p = p.rename(columns={"conId": "conid"})
            if "conid" not in p.columns:
                p["conid"] = pd.NA
            # Select only relevant columns; tolerate missing by filling
            for c in ("right", "strike", "secType"):
                if c not in p.columns:
                    p[c] = pd.NA
            p["conid"] = pd.to_numeric(p["conid"], errors="coerce")
            p = p.dropna(subset=["conid"]).copy()
            p["conid"] = p["conid"].astype(int)
            # Coerce strike to float where possible
            p["strike"] = pd.to_numeric(p["strike"], errors="coerce")
            pos_lookup = p.set_index("conid")[
                ["right", "strike", "secType"]
            ]
        except Exception:
            pos_lookup = pd.DataFrame(columns=["right", "strike", "secType"]).set_index(
                pd.Index([], name="conid")
            )

    # Numeric to string formatting helper: 0/1 decimal places
    fmt = lambda x: ("{:.1f}".format(float(x)).rstrip("0").rstrip("."))

    import ast

    results = {
        "strikes": [],
        "call_strikes": [],
        "put_strikes": [],
        "call_count": [],
        "put_count": [],
        "has_stock_leg": [],
    }

    # Helper to normalise entries from DB detail
    def _norm_db_leg(entry: dict) -> tuple[str, Optional[float], str]:
        right = str(entry.get("right") or "").upper()
        if right not in ("C", "P"):
            right = ""
        try:
            strike = float(entry.get("strike")) if entry.get("strike") is not None else None
        except Exception:
            strike = None
        sec_type = str(entry.get("secType") or "")
        return right, strike, sec_type

    for _, row in df.iterrows():
        v = row.get("legs")
        leg_ids: list[int] = []
        leg_dicts: list[dict] = []
        def _collect_from_seq(seq):
            nonlocal leg_ids, leg_dicts
            for x in seq:
                if isinstance(x, (int,)) or (isinstance(x, str) and str(x).lstrip("-").isdigit()):
                    try:
                        leg_ids.append(int(x))
                    except Exception:
                        pass
                elif isinstance(x, dict):
                    leg_dicts.append(x)
                elif isinstance(x, (list, tuple)):
                    # Support [right, strike, qty] or similar shapes
                    try:
                        right = str(x[0]).upper() if len(x) > 0 else ""
                    except Exception:
                        right = ""
                    try:
                        strike = float(x[1]) if len(x) > 1 and x[1] is not None else None
                    except Exception:
                        strike = None
                    entry = {"right": right if right in ("C", "P") else "", "strike": strike, "secType": None}
                    leg_dicts.append(entry)
                else:
                    # Unknown element type; ignore
                    pass

        if isinstance(v, (list, tuple)):
            _collect_from_seq(v)
        elif isinstance(v, str):
            s = v.strip()
            if s.startswith("[") and s.endswith("]"):
                try:
                    parsed = ast.literal_eval(s)
                    if isinstance(parsed, (list, tuple)):
                        _collect_from_seq(parsed)
                except Exception:
                    leg_ids = leg_ids  # keep whatever was collected

        call_k: set[float] = set()
        put_k: set[float] = set()
        call_n = 0
        put_n = 0
        stock_flag = False
        used_db = False

        source_tag = ""
        for cid in leg_ids:
            if cid in pos_lookup.index:
                rec = pos_lookup.loc[cid]
                # When duplicates exist, .loc may return a DataFrame; collapse to first row
                if isinstance(rec, pd.DataFrame):
                    rec = rec.iloc[0]
                right = (str(rec.get("right")) if pd.notna(rec.get("right")) else "").upper()
                strike = rec.get("strike")
                sec_type = str(rec.get("secType")) if pd.notna(rec.get("secType")) else ""
                if right == "C":
                    call_n += 1
                    if pd.notna(strike):
                        try:
                            call_k.add(float(strike))
                        except Exception:
                            pass
                elif right == "P":
                    put_n += 1
                    if pd.notna(strike):
                        try:
                            put_k.add(float(strike))
                        except Exception:
                            pass
                else:
                    # Non-option leg; treat empty right as stock if secType says so
                    pass
                if sec_type == "STK" or right == "":
                    stock_flag = True
                source_tag = source_tag or "pos"
            else:
                # Unknown conId: cannot resolve via positions; try to match from leg_dicts later
                used_db = used_db or False

        # Use dict-style legs from 'legs' column when present (works for live/engine sources that carry details)
        if leg_dicts:
            for ent in leg_dicts:
                if not isinstance(ent, dict):
                    continue
                right, strike, sec_type = _norm_db_leg(ent)
                if sec_type == "STK" or right == "":
                    stock_flag = True
                if right == "C":
                    call_n += 1
                    if strike is not None:
                        call_k.add(float(strike))
                elif right == "P":
                    put_n += 1
                    if strike is not None:
                        put_k.add(float(strike))

        # DB fallback: include legs from __db_legs_detail that positions lookup couldn't resolve
        db_detail = row.get("__db_legs_detail")
        if isinstance(db_detail, (list, tuple)) and db_detail:
            resolved_ids = set(leg_ids) & set(pos_lookup.index.tolist()) if len(pos_lookup.index) > 0 else set()
            for ent in db_detail:
                if not isinstance(ent, dict):
                    continue
                conid = ent.get("conid")
                try:
                    if conid is not None and int(conid) in resolved_ids:
                        continue
                except Exception:
                    pass
                right, strike, sec_type = _norm_db_leg(ent)
                if sec_type == "STK" or right == "":
                    stock_flag = True
                if right == "C":
                    call_n += 1
                    if strike is not None:
                        call_k.add(float(strike))
                    used_db = True
                elif right == "P":
                    put_n += 1
                    if strike is not None:
                        put_k.add(float(strike))
                    used_db = True
            if used_db and source_tag != "pos":
                source_tag = "db"

        # Compose output fields
        all_k = sorted(call_k.union(put_k))
        call_s = "/".join(fmt(x) for x in sorted(call_k)) if call_k else ""
        put_s = "/".join(fmt(x) for x in sorted(put_k)) if put_k else ""
        all_s = "/".join(fmt(x) for x in all_k) if all_k else ""

        results["strikes"].append(all_s)
        results["call_strikes"].append(call_s)
        results["put_strikes"].append(put_s)
        results["call_count"].append(int(call_n))
        results["put_count"].append(int(put_n))
        results["has_stock_leg"].append(bool(stock_flag))
        db_fallback_rows += 1 if used_db else 0
        results.setdefault("__strike_source", []).append(source_tag)

    for k, v in results.items():
        df[k] = v

    try:
        logger.info(
            "Combos enrichment: %d rows (calls=%d puts=%d) [db_fallback_rows=%d]",
            len(df),
            int(df["call_count"].sum()),
            int(df["put_count"].sum()),
            int(db_fallback_rows),
        )
    except Exception:
        pass

    # Optional debug CSV with strike source indicator
    try:
        if os.getenv("PE_DEBUG_COMBOS") == "1":
            dbg_df = df.copy()
            io_core.save(dbg_df, "combos_enriched_debug", "csv", config_core.settings.output_dir)
            # Do not propagate debug-only column to main df
            try:
                df = df.drop(columns=["__strike_source"], errors="ignore")
            except Exception:
                pass
    except Exception:
        pass

    return df


def _stable_combo_id(row: pd.Series) -> str:
    expiry = (
        pd.to_datetime(row.get("expiry"), errors="coerce").strftime("%Y-%m-%d")
        if row.get("expiry")
        else ""
    )
    legs = row.get("legs") or []
    parts: list = []
    if isinstance(legs, list):
        # If ints, treat as conId list
        if all(isinstance(x, (int,)) for x in legs):
            parts = sorted(int(x) for x in legs)
        else:
            for leg in legs:
                if isinstance(leg, dict):
                    parts.append((leg.get("right"), leg.get("strike"), leg.get("qty")))
                elif isinstance(leg, (list, tuple)):
                    right = leg[0] if len(leg) > 0 else None
                    strike = leg[1] if len(leg) > 1 else None
                    qty = leg[2] if len(leg) > 2 else None
                    parts.append((right, strike, qty))
                else:
                    parts.append(
                        (
                            getattr(leg, "right", None),
                            getattr(leg, "strike", None),
                            getattr(leg, "qty", None),
                        )
                    )
    sig = json.dumps(sorted(parts), sort_keys=True)
    payload = json.dumps(
        {"u": row.get("underlying"), "e": expiry, "t": row.get("type"), "s": row.get("structure"), "w": row.get("width"), "l": sig}, sort_keys=True
    )
    return hashlib.sha1(payload.encode()).hexdigest()


def _persist_combos(df: pd.DataFrame, positions_df: pd.DataFrame | None = None) -> int:
    """Upsert combos into SQLite DB. Returns number of rows written."""

    if df is None or df.empty:
        return 0
    db = os.environ.get("PE_DB_PATH") or (Path(settings.output_dir) / "combos.db")
    with sqlite3.connect(db) as con:
        # Ensure base tables exist (mirror of core.combos schema)
        _DDL = (
            "CREATE TABLE IF NOT EXISTS combos ("
            " combo_id TEXT PRIMARY KEY,"
            " ts_created TEXT,"
            " ts_closed TEXT,"
            " structure TEXT,"
            " underlying TEXT,"
            " expiry TEXT,"
            " type TEXT,"
            " width REAL,"
            " credit_debit REAL,"
            " parent_combo_id TEXT,"
            " closed_date TEXT"
            ");"
            "CREATE TABLE IF NOT EXISTS legs ("
            " combo_id TEXT,"
            " conid INTEGER,"
            " strike REAL,"
            " right TEXT,"
            " PRIMARY KEY(combo_id, conid)"
            ");"
        )
        try:
            con.executescript(_DDL)
        except Exception:
            pass
        io_core.migrate_combo_schema(con)
        cols = [c[1] for c in con.execute("PRAGMA table_info(combos);")]
        work = df.copy()
        if "combo_id" not in work.columns:
            if work.index.name == "combo_id":
                work = work.reset_index()
            work["combo_id"] = work.apply(_stable_combo_id, axis=1)
        elif work.index.name == "combo_id":
            work = work.reset_index()

        now = datetime.now(timezone.utc).isoformat()
        if "ts_created" in cols and "ts_created" not in work.columns:
            work["ts_created"] = now

        to_write = [c for c in work.columns if c in cols]
        rows = [tuple(r[c] for c in to_write) for _, r in work.iterrows()]
        placeholders = ",".join(["?"] * len(to_write))
        con.executemany(
            f"INSERT OR REPLACE INTO combos ({','.join(to_write)}) VALUES ({placeholders})",
            rows,
        )
        # Backfill legs if provided
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS legs ( combo_id TEXT, conid INTEGER, strike REAL, right TEXT, PRIMARY KEY(combo_id, conid) )"
            )
        except Exception:
            pass
        if "legs" in work.columns:
            # Normalize a positions lookup if available
            pos_lookup = None
            if positions_df is not None and not positions_df.empty:
                try:
                    p = positions_df.copy()
                    if "conId" in p.columns:
                        p = p.rename(columns={"conId": "conid"})
                    elif "conid" not in p.columns:
                        p["conid"] = pd.NA
                    pos_lookup = p.set_index("conid")
                except Exception:
                    pos_lookup = None
            inserts = []
            for _, rr in work.iterrows():
                cmb_id = rr.get("combo_id")
                v = rr.get("legs")
                if isinstance(v, str) and v.startswith("["):
                    try:
                        import ast
                        v = ast.literal_eval(v)
                    except Exception:
                        v = []
                if not isinstance(v, (list, tuple)):
                    continue
                for cid in v:
                    try:
                        cc = int(cid)
                    except Exception:
                        continue
                    k_strike = None
                    k_right = None
                    if pos_lookup is not None and cc in pos_lookup.index:
                        try:
                            ks = pos_lookup.loc[cc].get("strike")
                            try:
                                k_strike = float(ks) if ks is not None else None
                            except Exception:
                                k_strike = None
                            k_right = pos_lookup.loc[cc].get("right")
                        except Exception:
                            pass
                    inserts.append((cmb_id, cc, k_strike, k_right))
            if inserts:
                con.executemany(
                    "INSERT OR IGNORE INTO legs (combo_id, conid, strike, right) VALUES (?,?,?,?)",
                    inserts,
                )
        con.commit()
        return len(rows)


def _fmt_float(x: Optional[float]) -> str:
    try:
        return f"{x:,.2f}"
    except Exception:
        return "-"


def _print_totals(console: Console, totals_df: Optional[pd.DataFrame]) -> None:
    if totals_df is None or totals_df.empty:
        return
    t = Table(title="Totals", box=box.SIMPLE_HEAVY)
    for col in totals_df.columns:
        t.add_column(col, justify="right")
    for _, row in totals_df.iterrows():
        t.add_row(
            *[
                _fmt_float(row[c]) if isinstance(row[c], (int, float)) else str(row[c])
                for c in totals_df.columns
            ]
        )
    console.print(t)


def _print_positions(console: Console, pos_df: Optional[pd.DataFrame]) -> None:
    if pos_df is None or pos_df.empty:
        return
    cols = [
        c
        for c in [
            "symbol",
            "qty",
            "price",
            "delta",
            "gamma",
            "theta",
            "vega",
            "greeks_source",
        ]
        if c in pos_df.columns
    ]
    t = Table(title="Positions", box=box.SIMPLE_HEAVY)
    t.add_column("Symbol")
    if "qty" in cols:
        t.add_column("Qty", justify="right")
    if "price" in cols:
        t.add_column("Price", justify="right")
    for c in ["delta", "gamma", "theta", "vega"]:
        if c in cols:
            t.add_column(c.capitalize(), justify="right")
    if "greeks_source" in cols:
        t.add_column("Src", justify="center")
    for _, r in pos_df.iterrows():
        row = [str(r.get("symbol", ""))]
        if "qty" in cols:
            row.append(_fmt_float(r.get("qty")))
        if "price" in cols:
            row.append(_fmt_float(r.get("price")))
        for c in ["delta", "gamma", "theta", "vega"]:
            if c in cols:
                row.append(_fmt_float(r.get(c)))
        if "greeks_source" in cols:
            row.append(str(r.get("greeks_source") or ""))
        t.add_row(*row)
    console.print(t)


def _print_combos(console: Console, combos_df: Optional[pd.DataFrame]) -> None:
    if combos_df is None or combos_df.empty:
        console.print("Combos: (no combos)")
        return

    # Prefer structure_label if present; fall back to structure
    struct_col = "structure_label" if "structure_label" in combos_df.columns else "structure"
    base_order = [
        "underlying",
        "expiry",
        struct_col,
        "type",
        "legs_n" if "legs_n" in combos_df.columns else "legs",
        "width",
        "unrealized_pnl",
        "unrealized_pnl_pct",
        "strikes",
        "call_strikes",
        "put_strikes",
        "call_count",
        "put_count",
        "has_stock_leg",
    ]
    present = [c for c in base_order if c in combos_df.columns]
    t = Table(title="Combos", box=box.SIMPLE_HEAVY)
    for col in present:
        right_cols = {"width", "qty", "legs", "legs_n", "call_count", "put_count"}
        justify = "right" if col in right_cols else "left"
        t.add_column(col.capitalize().replace("_", " "), justify=justify)
    for _, r in combos_df.iterrows():
        cells = []
        for col in present:
            val = r.get(col, "")
            if isinstance(val, (int, float)) and col in {"width", "qty", "legs", "legs_n", "call_count", "put_count"}:
                cells.append(_fmt_float(val))
            else:
                cells.append(str(val) if val is not None else "")
        t.add_row(*cells)
    console.print(t)


def run(
    fmt: str = "csv",
    write_positions: bool = True,
    write_totals: bool = True,
    return_dict: bool = False,
    combos: bool = True,
    combo_types: str = "simple",
    combos_source: str = "auto",
    persist_combos: bool = False,
    *,
    output_dir: str | Path | None = None,
    return_frames: bool = False,
) -> Any:
    """Aggregate per-position Greeks and optionally persist the results."""

    outdir = Path(output_dir or config_core.settings.output_dir).expanduser()
    try:
        os.makedirs(outdir, exist_ok=True)
    except Exception:
        pass

    # Optional offline positions override
    positions_override: pd.DataFrame | None = None
    if "args" in globals() and getattr(globals()["args"], "positions_csv", None):
        try:
            positions_override = pd.read_csv(os.path.expanduser(globals()["args"].positions_csv))
            logger.info(
                f"Loaded positions from CSV: {globals()['args'].positions_csv} rows={len(positions_override)}"
            )
        except Exception as e:
            logger.error(f"Failed to read --positions-csv: {e}")
            positions_override = None

    pos_df: pd.DataFrame
    if positions_override is None:
        pos_df = run_with_spinner("Fetching positions…", _load_positions).copy()
    else:
        csv_df = positions_override.copy()
        for col in ["delta", "gamma", "vega", "theta", "multiplier"]:
            if col not in csv_df.columns:
                csv_df[col] = np.nan
        if "symbol" not in csv_df.columns and "underlying" in csv_df.columns:
            csv_df["symbol"] = csv_df["underlying"]
        # Build a minimal positions DataFrame compatible with downstream logic
        cols = [
            "symbol",
            "secType",
            "expiry",
            "strike",
            "right",
            "qty",
            "multiplier",
            "underlying",
            "conId",
            "delta",
            "gamma",
            "vega",
            "theta",
        ]
        for c in cols:
            if c not in csv_df.columns:
                csv_df[c] = np.nan
        pos_df = csv_df[cols].copy()
        # synthesize conId if missing
        if pos_df.get("conId").isna().any():
            def _synth(row):
                try:
                    v = row.get("conId")
                    if pd.notna(v):
                        return int(v)
                except Exception:
                    pass
                key = f"{row.get('underlying','')}|{row.get('expiry','')}|{row.get('right','')}|{row.get('strike','')}"
                import hashlib as _hl
                return -int(int.from_bytes(_hl.sha1(key.encode()).digest()[:4], 'big'))
            pos_df["conId"] = pos_df.apply(_synth, axis=1).astype("Int64")
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

    pos_df.loc[(pos_df.secType == "OPT") & (pos_df.multiplier.isna()), "multiplier"] = (
        100
    )
    pos_df.loc[pos_df.secType.isin(["STK", "ETF"]), "multiplier"] = 1

    if "greeks_source" not in pos_df.columns:
        pos_df["greeks_source"] = "IB"
    else:
        pos_df["greeks_source"] = pos_df["greeks_source"].apply(
            lambda v: (
                "IB" if v in (True, 1, "IB") else "BS" if v in (False, 0, "BS") else ""
            )
        )

    # Ensure numeric types for exposure math
    for col in ["qty", "multiplier", "delta", "gamma", "vega", "theta"]:
        try:
            pos_df[col] = pd.to_numeric(pos_df[col], errors="coerce").astype(float).fillna(0.0)
        except Exception:
            pos_df[col] = 0.0
    # Compute per-row exposures explicitly as float to avoid dtype quirks
    for greek in ["delta", "gamma", "vega", "theta"]:
        try:
            pos_df[f"{greek}_exposure"] = (
                pos_df[greek].astype(float)
                * pos_df["qty"].astype(float)
                * pos_df["multiplier"].astype(float)
            ).astype(float)
        except Exception:
            pos_df[f"{greek}_exposure"] = 0.0

    # Fallback: if all exposures are exactly zero but inputs suggest non-zero, recompute defensively
    try:
        exp_cols = [f"{g}_exposure" for g in ["delta", "gamma", "vega", "theta"]]
        if pos_df[exp_cols].abs().sum(numeric_only=True).sum() == 0.0:
            base_delta = pd.to_numeric(pos_df.get("delta", 0.0), errors="coerce").fillna(0.0)
            base_qty = pd.to_numeric(pos_df.get("qty", 0.0), errors="coerce").fillna(0.0)
            base_mult = pd.to_numeric(pos_df.get("multiplier", 0.0), errors="coerce").fillna(0.0)
            # Only apply fallback if any base inputs are non-zero
            if (base_delta.abs().sum() > 0) and (base_qty.abs().sum() > 0):
                pos_df["delta_exposure"] = (base_delta * base_qty * base_mult).astype(float)
                pos_df["gamma_exposure"] = (
                    pd.to_numeric(pos_df.get("gamma", 0.0), errors="coerce").fillna(0.0)
                    * base_qty
                    * base_mult
                ).astype(float)
                pos_df["vega_exposure"] = (
                    pd.to_numeric(pos_df.get("vega", 0.0), errors="coerce").fillna(0.0)
                    * base_qty
                    * base_mult
                ).astype(float)
                pos_df["theta_exposure"] = (
                    pd.to_numeric(pos_df.get("theta", 0.0), errors="coerce").fillna(0.0)
                    * base_qty
                    * base_mult
                ).astype(float)
    except Exception:
        pass

    # Totals computed directly from precomputed exposures for robustness
    try:
        totals = (
            pos_df[[f"{g}_exposure" for g in ["delta", "gamma", "vega", "theta"]]]
            .sum()
            .to_frame()
            .T
        )
        # Ensure plain Python floats
        for g in ["delta", "gamma", "vega", "theta"]:
            col = f"{g}_exposure"
            totals[col] = float(totals[col].iloc[0]) if not totals.empty else 0.0
    except Exception:
        totals = pd.DataFrame(
            {
                "delta_exposure": 0.0,
                "gamma_exposure": 0.0,
                "vega_exposure": 0.0,
                "theta_exposure": 0.0,
            },
            index=[0],
        )

    combos_df = pd.DataFrame()
    resolved_source = "none"
    if combos:
        combos_df, resolved_source = _choose_combos_df(
            combos_source, pos_df, combo_types
        )
        # Enrich with per-leg strike details (before saving/printing)
        try:
            combos_df = _enrich_combo_strikes(combos_df, positions_df=pos_df)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Combos enrichment failed: %s", exc)

        # Self-heal missing legs when sourcing from DB
        try:
            if resolved_source == "db":
                # Identify rows with empty/none legs
                def _legs_empty(v: object) -> bool:
                    if isinstance(v, (list, tuple)):
                        return len([x for x in v if x is not None]) == 0
                    import ast
                    if isinstance(v, str) and v.strip().startswith("["):
                        try:
                            parsed = ast.literal_eval(v)
                            return not isinstance(parsed, (list, tuple)) or len([x for x in parsed if x is not None]) == 0
                        except Exception:
                            return True
                    return True

                mask_empty = combos_df.get("legs").apply(_legs_empty) if "legs" in combos_df.columns else pd.Series([False] * len(combos_df))
                if bool(mask_empty.any()):
                    # Detect live combos once
                    try:
                        live_df = combo_core.detect_from_positions(pos_df)
                    except Exception:
                        live_df = pd.DataFrame(columns=["underlying","expiry","type","structure_label","legs","width"]) 

                    # Build helper keys for matching
                    def _norm_exp(s: str) -> str:
                        try:
                            return pd.to_datetime(str(s)).date().isoformat()
                        except Exception:
                            return str(s)

                    def _key(df_row: pd.Series) -> tuple:
                        return (
                            str(df_row.get("underlying", "")),
                            _norm_exp(df_row.get("expiry", "")),
                            str(df_row.get("type", "")) or str(df_row.get("structure", "")) or str(df_row.get("structure_label", "")),
                        )

                    # Precompute live map by key -> list of rows
                    live_groups: dict[tuple, list[pd.Series]] = {}
                    for _, r in live_df.iterrows():
                        live_groups.setdefault(_key(r), []).append(r)

                    healed = 0
                    new_legs: list[object] = []
                    healed_flags: list[bool] = []
                    for i, r in combos_df.iterrows():
                        if not mask_empty.loc[i]:
                            new_legs.append(r.get("legs"))
                            healed_flags.append(False)
                            continue
                        cand = live_groups.get(_key(r), [])
                        match_row: Optional[pd.Series] = None
                        if len(cand) == 1:
                            match_row = cand[0]
                        elif len(cand) > 1:
                            # choose by width proximity then max legs overlap on strike/right if possible
                            def _width(x):
                                try:
                                    return float(x.get("width")) if pd.notna(x.get("width")) else 0.0
                                except Exception:
                                    return 0.0
                            target_w = _width(r)
                            cand_sorted = sorted(cand, key=lambda x: abs(_width(x) - target_w))
                            match_row = cand_sorted[0]
                        if match_row is not None and isinstance(match_row.get("legs"), (list, tuple)) and len(match_row.get("legs")) > 0:
                            new_legs.append(list(match_row.get("legs")))
                            healed_flags.append(True)
                            healed += 1
                        else:
                            new_legs.append(r.get("legs"))
                            healed_flags.append(False)

                    if healed > 0:
                        combos_df = combos_df.copy()
                        combos_df["legs"] = new_legs
                        combos_df["__healed_legs"] = healed_flags
                        # Re-enrich strikes with new legs
                        try:
                            combos_df = _enrich_combo_strikes(combos_df, positions_df=pos_df)
                        except Exception:
                            pass
                        # Optionally persist healed legs into DB
                        if persist_combos:
                            try:
                                _persist_combos(combos_df, positions_df=pos_df)
                                persisted = True
                            except Exception:
                                persisted = False
                        else:
                            persisted = False
                        logger.info("Combos self-heal: healed_rows=%d (persisted=%s)", healed, "yes" if persisted else "no")
        except Exception as exc:
            logger.warning("Combos self-heal failed: %s", exc)

        # Ensure 'legs' is a parsed list and recompute legs_n before saving/persisting
        try:
            import json as _json
            def _parse_legs(v):
                if isinstance(v, list):
                    return v
                if isinstance(v, str):
                    s = v.strip()
                    if s.startswith("[") and s.endswith("]"):
                        try:
                            return _json.loads(s)
                        except Exception:
                            return []
                return []
            if "legs" in combos_df.columns:
                combos_df["legs"] = combos_df["legs"].apply(_parse_legs)
                combos_df["legs_n"] = combos_df["legs"].apply(lambda x: len(x) if isinstance(x, list) else 0).astype("Int64")
            # Compute unrealized P&L per combo from per-leg P&L (pnl_leg) in positions
            try:
                pmap = pos_df.copy()
                # Normalize conId as integer index for lookup
                if "conId" in pmap.columns:
                    try:
                        pmap["conId"] = pd.to_numeric(pmap["conId"], errors="coerce").astype("Int64")
                    except Exception:
                        pass
                    pmap = pmap.set_index("conId", drop=False)
                else:
                    pmap.index = pd.Index([], name="conId")
                def _sum_pnl(legs):
                    total = 0.0
                    if not isinstance(legs, list):
                        return float("nan")
                    has_any = False
                    for cid in legs:
                        try:
                            ic = int(cid)
                        except Exception:
                            continue
                        if ic in pmap.index:
                            try:
                                val = float(pmap.loc[ic].get("pnl_leg", float("nan")))
                            except Exception:
                                val = float("nan")
                            if not math.isnan(val):
                                total += val
                                has_any = True
                    return total if has_any else float("nan")

                def _sum_basis(legs):
                    # Sum entry basis using per-unit avg cost × qty × multiplier
                    total = 0.0
                    got = False
                    if not isinstance(legs, list):
                        return float("nan")
                    for cid in legs:
                        try:
                            ic = int(cid)
                        except Exception:
                            continue
                        if ic in pmap.index:
                            row = pmap.loc[ic]
                            try:
                                ac = row.get("avg_cost_unit", float("nan"))
                                q = row.get("qty", float("nan"))
                                m = row.get("multiplier", float("nan"))
                                v = float(ac) * float(q) * float(m)
                            except Exception:
                                v = float("nan")
                            if not math.isnan(v):
                                total += v
                                got = True
                    return total if got else float("nan")

                combos_df["unrealized_pnl"] = combos_df["legs"].apply(_sum_pnl)
                combos_df["credit_debit"] = combos_df.get("credit_debit", np.nan)
                combos_df["credit_debit"] = combos_df.apply(
                    lambda r: _sum_basis(r.get("legs")) if (pd.isna(r.get("credit_debit")) or r.get("credit_debit") is None) else r.get("credit_debit"),
                    axis=1,
                )

                # Percent vs. net debit/credit; fallback to width-based notional if basis is missing
                def _pct_row(r):
                    pnl = r.get("unrealized_pnl")
                    basis = r.get("credit_debit")
                    try:
                        if basis is not None and not math.isnan(float(basis)) and abs(float(basis)) > 1e-6:
                            return float(pnl) / abs(float(basis)) * 100.0
                    except Exception:
                        pass
                    # Fallback: width * multiplier * lots
                    try:
                        width = float(r.get("width", float("nan")))
                        if math.isnan(width) or width <= 0:
                            return float("nan")
                        # Estimate lots from legs' absolute qty minimum
                        legs = r.get("legs")
                        if not isinstance(legs, list) or not legs:
                            return float("nan")
                        qs = []
                        for cid in legs:
                            try:
                                ic = int(cid)
                            except Exception:
                                continue
                            if ic in pmap.index:
                                try:
                                    qs.append(abs(float(pmap.loc[ic].get("qty", float("nan")))))
                                except Exception:
                                    continue
                        lots = min(qs) if qs else float("nan")
                        mult = float(pmap.loc[int(legs[0])].get("multiplier", 100.0)) if isinstance(legs, list) and legs and int(legs[0]) in pmap.index else 100.0
                        denom = width * mult * lots
                        if denom and not math.isnan(denom) and denom > 0:
                            return float(pnl) / denom * 100.0
                    except Exception:
                        return float("nan")
                    return float("nan")

                combos_df["unrealized_pnl_pct"] = combos_df.apply(_pct_row, axis=1)
            except Exception:
                pass
        except Exception:
            pass

        # Optional debug dump of enriched combos
        if os.getenv("PE_DEBUG_COMBOS"):
            try:
                logger.info(
                    "Combos enriched columns: %s", list(combos_df.columns)
                )
                logger.info("Combos enriched head: \n%s", combos_df.head(3).to_string())
                try:
                    io_core.save(
                        combos_df,
                        "combos_enriched_debug",
                        fmt,
                        outdir,
                    )
                except Exception:
                    pass
            except Exception:
                pass

        if persist_combos and resolved_source in {"live", "engine"}:
            try:
                count = _persist_combos(combos_df, positions_df=pos_df)
                logger.info("Combos persisted: %d", count)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Persist combos failed: %s", exc)

    if write_positions:
        io_core.save(pos_df, "portfolio_greeks_positions", fmt, outdir)
    if write_totals:
        io_core.save(totals, "portfolio_greeks_totals", fmt, outdir)
        if combos:
            # Drop auxiliary columns from CSV output
            save_df = combos_df.drop(columns=["__db_legs_detail", "__strike_source", "__healed_legs"], errors="ignore")
            io_core.save(save_df, "portfolio_greeks_combos", fmt, outdir)
            logger.info("Combos saved: %d", len(combos_df))

    if os.getenv("PE_QUIET") in (None, "", "0"):
        print(f"✅ Greeks exported → {outdir}")

    no_pretty = False
    if "args" in globals():
        no_pretty = getattr(globals()["args"], "no_pretty", False)
    # Honor PE_QUIET by suppressing Rich pretty printing
    if os.getenv("PE_QUIET") not in (None, "", "0"):
        no_pretty = True
    use_pretty = (not no_pretty) and sys.stdout.isatty()
    if use_pretty:
        console = Console()
        try:
            _print_totals(console, totals)
        except Exception:
            pass
        try:
            _print_positions(console, pos_df)
        except Exception:
            pass
        if combos:
            try:
                _print_combos(console, combos_df)
            except Exception:
                pass

    if return_dict:
        totals_row = totals.iloc[0].to_dict()
        combo_sum: Dict[str, float] = {}
        if (
            combos
            and not combos_df.empty
            and {"delta", "gamma", "vega", "theta"}.issubset(combos_df.columns)
        ):
            combo_sum = combos_df[["delta", "gamma", "vega", "theta"]].sum().to_dict()
        result = {"legs": totals_row, "combos": combo_sum}
        if return_frames:
            return result, pos_df, totals, combos_df
        return result
    if return_frames:
        return pos_df, totals, combos_df
    return None


def main(argv: list[str] | None = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Portfolio Greeks exporter")
    parser.add_argument("--positions-csv")
    parser.add_argument("--no-combos", action="store_true")
    parser.add_argument(
        "--combo-types", choices=["simple", "all"], default="simple"
    )
    parser.add_argument(
        "--combos-source",
        choices=["auto", "db", "live", "engine"],
        default="auto",
    )
    parser.add_argument("--persist-combos", action="store_true")
    parser.add_argument("--debug-combos", action="store_true")
    parser.add_argument("--no-pretty", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-dir")
    parser.add_argument("--no-files", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args(argv)

    if args.preflight:
        from portfolio_exporter.core import schemas as pa_schemas

        warnings: list[str] = []
        ok = True
        if args.positions_csv:
            try:
                df = pd.read_csv(os.path.expanduser(args.positions_csv))
            except Exception as e:
                warnings.append(str(e))
                ok = False
            else:
                msgs = pa_schemas.check_headers("positions", df)
                warnings.extend(msgs)
                if msgs and not any("pandera" in m for m in msgs):
                    ok = False
        else:
            warnings.append("--positions-csv required for preflight")
            ok = False
        summary = json_helpers.report_summary({}, outputs={}, warnings=warnings, meta={"script": "portfolio_greeks"})
        summary["ok"] = ok
        if args.json:
            cli_helpers.print_json(summary, True)
        return summary

    globals()["args"] = args
    if args.debug_combos:
        os.environ["PE_DEBUG_COMBOS"] = "1"

    formats = cli_helpers.decide_file_writes(
        args,
        json_only_default=True,
        defaults={
            "positions": bool(args.output_dir),
            "totals": bool(args.output_dir),
            "combos": bool(args.output_dir) and not args.no_combos,
        },
    )
    outdir = cli_helpers.resolve_output_dir(args.output_dir)
    quiet, _pretty = cli_helpers.resolve_quiet(args.no_pretty)

    with RunLog(script="portfolio_greeks", args=vars(args), output_dir=outdir) as rl:
        pos_df, totals, combos_df = run(
            fmt="csv",
            write_positions=formats["positions"],
            write_totals=formats["totals"],
            combos=formats["combos"],
            combo_types=args.combo_types,
            combos_source=args.combos_source,
            persist_combos=args.persist_combos,
            output_dir=outdir,
            return_frames=True,
        )

        outputs: Dict[str, str] = {}
        written: list[Path] = []
        if formats["positions"]:
            p = Path(outdir) / "portfolio_greeks_positions.csv"
            outputs["positions"] = str(p)
            written.append(p)
        if formats["totals"]:
            p = Path(outdir) / "portfolio_greeks_totals.csv"
            outputs["totals"] = str(p)
            written.append(p)
            if formats["combos"]:
                pc = Path(outdir) / "portfolio_greeks_combos.csv"
                outputs["combos"] = str(pc)
                written.append(pc)

        rl.add_outputs(written)
        manifest_path = rl.finalize(write=bool(written))

        summary = json_helpers.report_summary(
            {
                "positions": len(pos_df),
                "totals": 1,
                "combos": len(combos_df),
            },
            outputs=outputs,
            meta={"script": "portfolio_greeks"},
        )
        if manifest_path:
            summary["outputs"].append(str(manifest_path))
        if args.json:
            cli_helpers.print_json(summary, quiet)
        return summary


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
