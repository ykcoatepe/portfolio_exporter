#!/usr/bin/env python3
"""
option_chain_snapshot.py  –  Export a full option-chain snapshot for one or more symbols

• Uses IBKR market-data (ib_insync) and writes CSVs to your iCloud Downloads dir.
• Handles live, frozen, delayed-streaming *or* delayed-snapshot data automatically.
• If Greeks / IV or bid/ask are still missing after streaming, it takes a one-shot
  delayed snapshot for each affected contract to fill the gaps.

Usage
=====
# snapshot every underlying currently held in the IB account
$ python option_chain_snapshot.py

# snapshot only MSFT and QQQ
$ python option_chain_snapshot.py --symbols MSFT,QQQ

# snapshot TSLA for two expiries and AAPL for one
$ python option_chain_snapshot.py --symbol-expiries 'TSLA:20250620,20250703;AAPL:20250620'
"""

import argparse
import csv
import logging
import math
from typing import Any
import os
import sys
import time
from datetime import datetime, timezone, date
from typing import List, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf
from ib_insync import IB, Option, Stock
from utils.bs import bs_greeks

try:  # optional dependencies
    import xlsxwriter  # type: ignore
except Exception:  # pragma: no cover - optional
    xlsxwriter = None  # type: ignore

try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
except Exception:  # pragma: no cover - optional
    SimpleDocTemplate = Table = TableStyle = colors = letter = landscape = None

from bisect import bisect_left


# ── helper: get reliable split‑adjusted spot ──
def _safe_spot(ib: IB, stk: Stock, streaming_tk):
    """
    Return a trustworthy spot:
      • live/frozen bid/ask or last if available
      • else previous regular‑session close (split‑adjusted).
    """
    spot_val = streaming_tk.marketPrice() or streaming_tk.last
    if spot_val and spot_val > 0:
        return spot_val
    # pull adjusted close (1‑day bar, regular trading hours)
    bars = ib.reqHistoricalData(
        stk,
        endDateTime="",
        durationStr="1 D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
    )
    return bars[-1].close if bars else np.nan


# ─────────── contract resolution helper ───────────
def _resolve_contract(ib: IB, template: Option):
    """
    Return a fully‑qualified Contract for the given template, handling
    ambiguous matches via `ib.qualifyContracts` first (fast‑path) and
    falling back to `reqContractDetails` only if qualification fails.

    Preference order for ambiguous matches:
      1. tradingClass equal to the underlying symbol
      2. first contract returned by IB

    Returns None if no contract can be qualified.
    """
    # --- fast path: qualifyContracts ----------------------------------------------------
    try:
        ql = ib.qualifyContracts(template)
        if ql:
            # If there is only one qualified contract, use it immediately
            if len(ql) == 1:
                return ql[0]
            # More than one – pick by tradingClass heuristics
            for c in ql:
                if c.tradingClass == template.symbol:
                    return c
            return ql[0]
    except Exception:
        # qualification can raise when template is too fuzzy – fall through
        pass

    # --- slow path: reqContractDetails --------------------------------------------------
    cds = ib.reqContractDetails(template)
    if not cds:
        return None
    if len(cds) == 1:
        return cds[0].contract
    for cd in cds:
        if cd.contract.tradingClass == template.symbol:
            return cd.contract
    return cds[0].contract


# ───────────────────────── CONFIG ──────────────────────────
OUTPUT_DIR = (
    "/Users/yordamkocatepe/Library/Mobile Documents/" "com~apple~CloudDocs/Downloads"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

PORTFOLIO_FILES = ["tickers_live.txt", "tickers.txt"]

IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7497, 10
LOG_FMT = "%(asctime)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)

logger = logging.getLogger(__name__)
# silence routine IBKR chatter – only show CRITICAL
for _n in ("ib_insync", "ib_insync.ib", "ib_insync.wrapper"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)

# optional progress bar
try:
    from tqdm import tqdm

    PROGRESS = True
except ImportError:
    PROGRESS = False

# ---------------------------------------------------------------------------


def load_tickers_from_files() -> List[str]:
    """Read tickers from the first portfolio file that exists."""
    path = next((p for p in PORTFOLIO_FILES if os.path.exists(p)), None)
    if not path:
        return []
    with open(path) as fh:
        return [ln.strip().upper() for ln in fh if ln.strip()]


def get_portfolio_tickers(ib: IB) -> List[str]:
    """Return all stock / ETF symbols currently held in the account."""
    tickers: set[str] = {
        pos.contract.symbol.upper()
        for pos in ib.portfolio()
        if pos.contract.secType == "STK"
    }
    return sorted(tickers)


# ────────────── expiry helpers ──────────────
def choose_expiry(expirations: Sequence[str]) -> str:
    """Pick weekly ≤ 7 days, else first Friday, else earliest."""
    today = datetime.utcnow().date()
    # within a week
    for e in expirations:
        if (datetime.strptime(e, "%Y%m%d").date() - today).days <= 7:
            return e
    # first Friday
    for e in expirations:
        if datetime.strptime(e, "%Y%m%d").weekday() == 4:
            return e
    return expirations[0]


def pick_expiry_with_hint(expirations: Sequence[str], hint: str | None) -> str:
    """
    Smart expiry picker that honours a user *hint*.

    Supported hint formats:
    • exact ``YYYYMMDD`` → use if available
    • ``YYYYMM`` prefix → choose 3rd Friday of that month, else first expiry
    • month name/abbr (``july``) → same logic across any year
    • ``day month`` (``26 jun``/``jun 26``/``26/06``) → nearest expiry on or
      after that date
    • otherwise falls back to :func:`choose_expiry`.
    """
    if not expirations:
        raise ValueError("Expirations list cannot be empty.")
    expirations = sorted(expirations)

    if not hint:
        return choose_expiry(expirations)

    hint = hint.strip().lower()
    if not hint:
        return choose_expiry(expirations)

    # exact date
    if len(hint) == 8 and hint.isdigit() and hint in expirations:
        return hint

    # helper
    def third_friday(yyyymmdd: str) -> bool:
        dt = datetime.strptime(yyyymmdd, "%Y%m%d")
        return dt.weekday() == 4 and 15 <= dt.day <= 21

    # YYYYMM prefix
    if len(hint) == 6 and hint.isdigit():
        m = [e for e in expirations if e.startswith(hint)]
        if m:
            fridays = [e for e in m if third_friday(e)]
            return fridays[0] if fridays else m[0]

    # month name / abbr
    # day + month input
    def parse_day_month(h: str) -> tuple[int, int] | tuple[None, None]:
        fmts = ["%d %b", "%d %B", "%b %d", "%B %d", "%d/%m", "%d-%m", "%d.%m"]
        for fmt in fmts:
            try:
                dt = datetime.strptime(h, fmt)
                return dt.day, dt.month
            except ValueError:
                continue
        return None, None

    day, month = parse_day_month(hint)
    if day:
        first_year = datetime.strptime(expirations[0], "%Y%m%d").year
        candidate = date(first_year, month, day)
        for e in expirations:
            ed = datetime.strptime(e, "%Y%m%d").date()
            if ed >= candidate:
                return e
        candidate = date(first_year + 1, month, day)
        for e in expirations:
            ed = datetime.strptime(e, "%Y%m%d").date()
            if ed >= candidate:
                return e

    try:
        month_idx = datetime.strptime(hint[:3], "%b").month
    except ValueError:
        month_idx = None
    if month_idx:
        same_month = [e for e in expirations if int(e[4:6]) == month_idx]
        if same_month:
            fridays = [e for e in same_month if third_friday(e)]
            return fridays[0] if fridays else same_month[0]

    return choose_expiry(expirations)


# ──────── per-symbol expiry map parser ────────
def parse_symbol_expiries(spec: str) -> dict[str, list[str]]:
    """Parse 'TSLA:20250620,20250703;AAPL:20250620' style strings."""
    mapping: dict[str, list[str]] = {}
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            sym, exp_str = part.split(":", 1)
            expiries = [e.strip() for e in exp_str.split(",") if e.strip()]
        else:
            sym, expiries = part, []
        sym = sym.strip().upper()
        if not sym:
            continue
        mapping.setdefault(sym, []).extend(expiries)
    return mapping


def prompt_symbol_expiries() -> dict[str, list[str]]:
    """Interactively build a symbol→expiry map."""
    result: dict[str, list[str]] = {}
    while True:
        symbol = input("Symbol (blank to finish): ").strip()
        if not symbol:
            break
        symbol = symbol.upper()
        exp = input(
            f"Expiries for {symbol} (comma-separated, blank for auto): "
        ).strip()
        entry = parse_symbol_expiries(f"{symbol}:{exp}" if exp else symbol)
        for sym, vals in entry.items():
            result.setdefault(sym, []).extend(vals)
    return result


# ─────────── Black–Scholes fallback (for delayed feeds) ───────────


# ─────────── snapshot helpers ───────────
def _g(tk, field):
    """Return greek/IV attribute if present – else NaN."""
    if hasattr(tk, field):
        val = getattr(tk, field)
        if val not in (None, -1):
            return val
    mg = getattr(tk, "modelGreeks", None)
    if mg:
        val = getattr(mg, field, np.nan)
        if val not in (None, -1):
            return val
    return np.nan


def _attr(tk, field):
    """Return a numeric ticker attribute or NaN if unavailable."""
    val = getattr(tk, field, np.nan)
    return np.nan if val in (None, -1) else val


# ── helper: robust open‑interest getter ──


def fetch_yf_open_interest(symbol: str, expiry: str) -> dict[tuple[float, str], int]:
    """
    Return {(strike, right): open_interest} for a given symbol‑expiry pair
    using yfinance.

    yfinance expects the expiry in 'YYYY‑MM‑DD' format, whereas IB returns
    'YYYYMMDD'.  We normalise the string first, then attempt to fetch.
    Falls back to {} on any error or if the dataframe is empty.
    """
    # normalise expiry to YYYY‑MM‑DD for yfinance
    if len(expiry) == 8 and expiry.isdigit():
        expiry_fmt = f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:]}"
    else:
        expiry_fmt = expiry

    try:
        oc = yf.Ticker(symbol).option_chain(expiry_fmt)
    except Exception as e:  # pragma: no cover – network failures
        logger.debug("yfinance OI fetch fail %s %s: %s", symbol, expiry_fmt, e)
        return {}

    mapping: dict[tuple[float, str], int] = {}
    for right, df in (("C", oc.calls), ("P", oc.puts)):
        if getattr(df, "empty", True):
            continue
        for _, row in df[["strike", "openInterest"]].dropna().iterrows():
            try:
                mapping[(float(row["strike"]), right)] = int(row["openInterest"])
            except Exception:
                continue
    return mapping


def _wait_for_snapshots(ib: IB, snaps: list[tuple], timeout=8.0):
    """Wait until all tickers have a non-None timestamp or timeout."""
    end = time.time() + timeout
    while time.time() < end:
        if all(getattr(tk, "time", None) for _, tk in snaps):
            break
        time.sleep(0.25)


def _wait_attr(tk, field: str, timeout: float = 2.0) -> None:
    """Poll ticker until attribute present or timeout."""
    end = time.time() + timeout
    while time.time() < end:
        val = getattr(tk, field, None)
        if val not in (None, -1):
            break
        time.sleep(0.25)


# ─────────── core chain routine ───────────
def snapshot_chain(ib: IB, symbol: str, expiry_hint: str | None = None) -> pd.DataFrame:
    logger.info("Snapshot %s", symbol)

    stk = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(stk)
    if not stk.conId:
        raise RuntimeError(f"Unable to qualify underlying {symbol}")

    chains = ib.reqSecDefOptParams(symbol, "", "STK", stk.conId)
    if not chains:
        raise RuntimeError("No option-chain data")

    # choose the chain with the richest strike list (the “real” OPRA feed),
    # fall back to the first one if all are empty
    chain = max(
        (c for c in chains if c.strikes),
        key=lambda c: len(c.strikes),
        default=chains[0],
    )
    logger.info(
        "Using chain %s (exchange=%s, strikes=%d, expiries=%d)",
        getattr(chain, "tradingClass", "<n/a>"),
        getattr(chain, "exchange", "<n/a>"),
        len(chain.strikes),
        len(chain.expirations),
    )
    expiry = pick_expiry_with_hint(sorted(chain.expirations), expiry_hint)

    # always fetch open interest from Yahoo Finance
    yf_open_interest = fetch_yf_open_interest(symbol, expiry)

    # trading class
    root_tc = (
        chain.tradingClasses[0]
        if getattr(chain, "tradingClasses", None)
        else getattr(chain, "tradingClass", symbol) or symbol
    )
    use_trading_class = bool(root_tc and root_tc != symbol)

    # ── spot price and ±20 strikes ────────────────────────────────
    strikes_all = sorted(chain.strikes)

    spot_tk = ib.reqMktData(stk, "", True, False)
    ib.sleep(0.5)

    spot = _safe_spot(ib, stk, spot_tk)

    if spot_tk.contract:
        ib.cancelMktData(spot_tk.contract)

    if np.isnan(spot):
        logger.warning("Could not obtain reliable spot price – using full strike list")
        strikes = strikes_all
    else:
        # if spot lies outside the strike lattice (e.g. right after a split) warn & keep full list
        if spot < strikes_all[0] or spot > strikes_all[-1]:
            logger.warning(
                "Spot %.2f is outside strike range %s‑%s (possible recent split); using full strike list.",
                spot,
                strikes_all[0],
                strikes_all[-1],
            )
            strikes = strikes_all
        else:
            idx = bisect_left(strikes_all, spot)
            start = max(0, idx - 20)
            end = min(len(strikes_all), idx + 21)
            strikes = strikes_all[start:end]
            logger.info(
                "Spot %.2f → selected %d strikes (%s‑%s)",
                spot,
                len(strikes),
                strikes[0],
                strikes[-1],
            )

    # ── build contracts and resolve ambiguities ──
    raw_templates = [
        Option(
            symbol,
            expiry,
            strike,
            right,
            exchange="SMART",
            currency="USD",
            tradingClass=root_tc,  # <‑‑ add this
        )
        for strike in strikes
        for right in ("C", "P")
    ]

    contracts: list[Option] = []
    for tmpl in raw_templates:
        # --- first try with tradingClass as provided (root_tc) -----------------
        c = _resolve_contract(ib, tmpl)

        # --- fallback #1: strip tradingClass if first attempt failed -----------
        if c is None and use_trading_class:
            tmpl_no_tc = Option(
                tmpl.symbol,
                tmpl.lastTradeDateOrContractMonth,
                tmpl.strike,
                tmpl.right,
                exchange=tmpl.exchange,
                currency=tmpl.currency,
            )
            c = _resolve_contract(ib, tmpl_no_tc)

        # --- fallback #2: use the underlying symbol as tradingClass ------------
        if c is None and use_trading_class and root_tc != symbol:
            tmpl_sym_tc = Option(
                tmpl.symbol,
                tmpl.lastTradeDateOrContractMonth,
                tmpl.strike,
                tmpl.right,
                exchange=tmpl.exchange,
                currency=tmpl.currency,
                tradingClass=symbol,  # use the underlying itself
            )
            c = _resolve_contract(ib, tmpl_sym_tc)

        if c:
            contracts.append(c)

    if not contracts:
        raise RuntimeError(
            "No option contracts qualified for the chosen strikes / expiry"
        )

    # stream market data (need streaming for generic-tick 101)
    snapshots = [
        (
            c,
            ib.reqMktData(
                c,
                "",  # let IB decide tick types; avoids eid errors
                snapshot=False,
                regulatorySnapshot=False,
            ),
        )
        for c in contracts
    ]
    _wait_for_snapshots(ib, snapshots)

    # cancel streams
    for _, snap in snapshots:
        ib.cancelMktData(snap.contract)

    # ── one-shot snapshot fallback for missing price/IV ──
    for con, tk in snapshots:
        price_missing = (tk.bid in (None, -1)) and (tk.last in (None, -1))
        iv_missing = math.isnan(_g(tk, "impliedVolatility"))
        if price_missing or iv_missing:
            snap = ib.reqMktData(
                con, "", True, False
            )  # snapshot: genericTickList must be empty
            ib.sleep(0.35)
            for fld in ("bid", "ask", "last", "close", "impliedVolatility"):
                val = getattr(snap, fld, None)
                if val not in (None, -1):
                    setattr(tk, fld, val)
            if getattr(snap, "modelGreeks", None):
                tk.modelGreeks = snap.modelGreeks
            # Copy volume if present
            if getattr(snap, "volume", None) not in (None, -1):
                tk.volume = snap.volume
            if snap.contract:
                ib.cancelMktData(snap.contract)

    # build rows
    ts_local = datetime.now(ZoneInfo("Europe/Istanbul"))
    ts = ts_local.isoformat()
    rows = []
    for con, tk in snapshots:
        oi_attr = "callOpenInterest" if con.right == "C" else "putOpenInterest"
        iv_val = _g(tk, "impliedVolatility")
        delta_val = _g(tk, "delta")
        gamma_val = _g(tk, "gamma")
        vega_val = _g(tk, "vega")
        theta_val = _g(tk, "theta")

        # Black-Scholes fallback if still NaN
        if any(np.isnan(x) for x in (delta_val, gamma_val, vega_val, theta_val)):
            if spot and iv_val and not np.isnan(iv_val):
                exp_dt = datetime.strptime(expiry, "%Y%m%d").replace(
                    tzinfo=timezone.utc
                )
                T = max(
                    (exp_dt - datetime.now(timezone.utc)).total_seconds()
                    / (365 * 24 * 3600),
                    1 / (365 * 24),
                )
                bs = bs_greeks(spot, con.strike, T, 0.01, iv_val, con.right == "C")
                delta_val = bs["delta"] if np.isnan(delta_val) else delta_val
                gamma_val = bs["gamma"] if np.isnan(gamma_val) else gamma_val
                vega_val = bs["vega"] if np.isnan(vega_val) else vega_val
                theta_val = bs["theta"] if np.isnan(theta_val) else theta_val

        mid_price = np.nan if any(np.isnan([tk.bid, tk.ask])) else (tk.bid + tk.ask) / 2

        rows.append(
            {
                "timestamp": ts,
                "symbol": symbol,
                "spot": spot,
                "expiry": expiry,
                "strike": con.strike,
                "right": con.right,
                "bid": tk.bid if tk.bid not in (None, -1) else np.nan,
                "ask": tk.ask if tk.ask not in (None, -1) else np.nan,
                "mid_price": mid_price,
                "iv": iv_val,
                "delta": delta_val,
                "gamma": gamma_val,
                "vega": vega_val,
                "theta": theta_val,
                "open_interest": yf_open_interest.get((con.strike, con.right), np.nan),
                "volume": _attr(tk, "volume"),
            }
        )

    df = (
        pd.DataFrame(rows).sort_values(["right", "strike"]).reset_index(drop=True)
        if rows
        else pd.DataFrame()
    )

    return df


def _save_excel(df: pd.DataFrame, path: str) -> None:
    with pd.ExcelWriter(
        path, engine="xlsxwriter", datetime_format="yyyy-mm-dd"
    ) as writer:
        df.to_excel(writer, sheet_name="Options", index=False, float_format="%.3f")


def _save_pdf(df: pd.DataFrame, path: str) -> None:
    rows_data = [df.columns.tolist()] + df.values.tolist()
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
                ("FONTSIZE", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
            ]
        )
    )
    doc.build([table])


# ─────────────────────────── MAIN ──────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Option-chain snapshot exporter")
    parser.add_argument(
        "--symbols", type=str, help="Comma-separated tickers (overrides portfolio)."
    )
    parser.add_argument(
        "--symbol-expiries",
        type=str,
        help=(
            "Semi-colon separated SYM:EXP list, e.g. 'TSLA:20250620,20250703;AAPL:20250620'."
        ),
    )
    out_grp = parser.add_mutually_exclusive_group()
    out_grp.add_argument(
        "--excel",
        action="store_true",
        help="Save the snapshot(s) in an Excel workbook instead of CSV.",
    )
    out_grp.add_argument(
        "--pdf",
        action="store_true",
        help="Save the snapshot(s) as a PDF report instead of CSV.",
    )
    args = parser.parse_args()

    if not args.excel and not args.pdf:
        try:
            choice = (
                input("Select output format [csv / excel / pdf] (default csv): ")
                .strip()
                .lower()
            )
        except EOFError:
            choice = ""
        if choice in {"excel", "xlsx"}:
            args.excel = True
        elif choice == "pdf":
            args.pdf = True

    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, IB_CID, timeout=10)

        # try live → frozen → delayed-streaming → delayed snapshot
        for _md_type in (1, 2, 3, 4):
            try:
                ib.reqMarketDataType(_md_type)
                break
            except Exception:
                continue
    except Exception as exc:
        logger.error("IBKR connection failed: %s", exc)
        sys.exit(1)

    # decide symbols / expiries
    interactive = False
    if args.symbol_expiries:
        if args.symbols:
            parser.error("--symbols cannot be used with --symbol-expiries")
        se_map = parse_symbol_expiries(args.symbol_expiries)
        symbols = list(se_map)
        interactive = False
    elif args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        se_map = {s: [] for s in symbols}
        interactive = False
    else:
        se_map = prompt_symbol_expiries()
        interactive = True
        if se_map:
            symbols = list(se_map)
        else:
            symbols = get_portfolio_tickers(ib) or load_tickers_from_files()
            se_map = {s: [] for s in symbols}

    if not symbols:
        logger.error("No symbols to process — aborting.")
        sys.exit(1)

    portfolio_mode = not args.symbols and not args.symbol_expiries and not se_map
    expiry_hint = None
    if not portfolio_mode and not args.symbol_expiries and not interactive:
        hint = input(
            "Desired expiry (YYYYMMDD / YYYYMM / month name / day month), leave empty for auto: "
        ).strip()
        expiry_hint = hint or None

    logger.info("Symbols: %s", ", ".join(symbols))
    iterable = tqdm(symbols, desc="Option snapshots") if PROGRESS else symbols

    date_tag = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y%m%d_%H%M")
    combined = []
    for sym in iterable:
        hints = se_map.get(sym, [expiry_hint])
        hints = hints or [expiry_hint]
        for hint in hints:
            try:
                df = snapshot_chain(ib, sym, hint)
                if df.empty:
                    logger.warning("%s %s – no data", sym, hint)
                    continue
                if portfolio_mode:
                    combined.append(df)
                else:
                    label = hint if hint else "auto"
                    out_base = os.path.join(
                        OUTPUT_DIR, f"option_chain_{sym}_{label}_{date_tag}"
                    )
                    if args.excel:
                        path = f"{out_base}.xlsx"
                        _save_excel(df, path)
                    elif args.pdf:
                        path = f"{out_base}.pdf"
                        _save_pdf(df, path)
                    else:
                        path = f"{out_base}.csv"
                        df.to_csv(
                            path,
                            index=False,
                            quoting=csv.QUOTE_MINIMAL,
                            float_format="%.3f",
                        )
                    logger.info("Saved %s (%d rows)", path, len(df))
            except Exception as e:
                logger.warning("%s %s – skipped: %s", sym, hint, e)

    if portfolio_mode and combined:
        df_all = pd.concat(combined, ignore_index=True)
        out_base = os.path.join(OUTPUT_DIR, f"option_chain_portfolio_{date_tag}")
        if args.excel:
            out_path = f"{out_base}.xlsx"
            _save_excel(df_all, out_path)
        elif args.pdf:
            out_path = f"{out_base}.pdf"
            _save_pdf(df_all, out_path)
        else:
            out_path = f"{out_base}.csv"
            df_all.to_csv(
                out_path, index=False, quoting=csv.QUOTE_MINIMAL, float_format="%.3f"
            )
        logger.info(
            "Saved consolidated portfolio snapshot → %s (%d rows)",
            out_path,
            len(df_all),
        )

    ib.disconnect()


if __name__ == "__main__":
    main()
