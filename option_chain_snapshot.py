#!/usr/bin/env python3
"""
option_chain_snapshot.py  –  Export a full option-chain snapshot for one or more symbols

• Uses live market-data snapshots from IBKR (ib_insync).
• Writes CSV(s) to the same iCloud Downloads directory used by tech_signals_ibkr.py

Usage examples
==============
# snapshot every underlying currently held in the IB account
$ python option_chain_snapshot.py

# snapshot only MSFT and QQQ
$ python option_chain_snapshot.py --symbols MSFT,QQQ
"""

import argparse
import csv
import os
import sys
import time
import logging
# optional progress bar
try:
    from tqdm import tqdm
    PROGRESS = True
except ImportError:
    PROGRESS = False
from datetime import datetime, timezone
from typing import List, Sequence

import numpy as np
import pandas as pd
from ib_insync import IB, Stock, Option

# ───────────────────────── CONFIG ──────────────────────────
OUTPUT_DIR = (
    "/Users/yordamkocatepe/Library/Mobile Documents/"
    "com~apple~CloudDocs/Downloads"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

PORTFOLIO_FILES = ["tickers_live.txt", "tickers.txt"]

IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7497, 10
LOG_FMT = "%(asctime)s %(levelname)s %(message)s"

logging.basicConfig(level=logging.INFO, format=LOG_FMT)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------


def load_tickers_from_files() -> List[str]:
    """Fallback: read tickers from the first portfolio file that exists."""
    path = next((p for p in PORTFOLIO_FILES if os.path.exists(p)), None)
    if not path:
        return []
    with open(path) as fh:
        return [ln.strip().upper() for ln in fh if ln.strip()]


def get_portfolio_tickers(ib: IB) -> List[str]:
    """Query IBKR for current stock/ETF positions."""
    tickers: set[str] = set()
    for pos in ib.portfolio():
        if pos.contract.secType == "STK":
            tickers.add(pos.contract.symbol.upper())
    return sorted(tickers)



def choose_expiry(expirations: Sequence[str]) -> str:
    """Pick the best expiry: weekly ≤7 days, else first Friday, else earliest."""
    today = datetime.utcnow().date()
    # Weekly (≤ 7 days)
    for e in expirations:
        if (datetime.strptime(e, "%Y%m%d").date() - today).days <= 7:
            return e
    # First Friday
    for e in expirations:
        if datetime.strptime(e, "%Y%m%d").weekday() == 4:
            return e
    return expirations[0]


# ────────────── Expiry picker with user hint ──────────────
def pick_expiry_with_hint(expirations: Sequence[str], hint: str | None) -> str:
    """
    If *hint* is supplied try to pick an expiry that matches it:
    • 8‑digit YYYYMMDD -> exact match
    • 6‑digit YYYYMM   -> first expiry that starts with that prefix
    • Month name/abbr  -> first expiry whose month matches (case‑insensitive)
    Falls back to choose_expiry() if nothing matches.
    """
    if not hint:
        return choose_expiry(expirations)

    hint = hint.strip()
    if not hint:
        return choose_expiry(expirations)

    # exact YYYYMMDD
    if len(hint) == 8 and hint.isdigit() and hint in expirations:
        return hint

    # YYYYMM prefix
    if len(hint) == 6 and hint.isdigit():
        for e in expirations:
            if e.startswith(hint):
                return e

    # month name
    try:
        month_idx = datetime.strptime(hint[:3], "%b").month  # Jan, Feb, …
    except ValueError:
        month_idx = None

    if month_idx:
        for e in expirations:
            if int(e[4:6]) == month_idx:
                return e

    # nothing matched – use default logic
    return choose_expiry(expirations)


def _wait_for_snapshots(ib: IB, snapshots: list[tuple]) -> None:
    """Wait up to ~8 s until all snapshots have non‑None time stamp."""
    deadline = time.time() + 8.0
    while time.time() < deadline:
        if all(getattr(tk, "time", None) for _, tk in snapshots):
            break
        time.sleep(0.25)


def _g(tk, field: str):
    """Return greek/IV attribute if present – else NaN."""
    if hasattr(tk, field):
        return getattr(tk, field)
    mg = getattr(tk, "modelGreeks", None)
    return getattr(mg, field, np.nan) if mg else np.nan


def snapshot_chain(ib: IB, symbol: str, expiry_hint: str | None = None) -> pd.DataFrame:
    """Return a DataFrame with the option-chain snapshot for one underlying."""
    logger.info("Snapshot %s", symbol)

    stk = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(stk)
    if not stk.conId:
        raise RuntimeError(f"Unable to qualify underlying {symbol}")

    chains = ib.reqSecDefOptParams(symbol, "", "STK", stk.conId)
    if not chains:
        raise RuntimeError("No option-chain data")

    chain = chains[0]
    expiry = pick_expiry_with_hint(sorted(chain.expirations), expiry_hint)

    # Determine the correct trading class field (plural, singular, or fallback)
    if hasattr(chain, "tradingClasses") and chain.tradingClasses:
        root_tc = chain.tradingClasses[0]
    elif hasattr(chain, "tradingClass") and getattr(chain, "tradingClass"):
        root_tc = chain.tradingClass
    else:
        root_tc = symbol  # fallback to the underlying ticker

    logger.debug(f"Using trading class '{root_tc}' for {symbol} options on expiry {expiry}.")

    # ── obtain spot price & trim strike list if chain is huge ──────────────────
    spot = None
    try:
        spot_tk = ib.reqMktData(stk, "", True, False)  # snapshot
        ib.sleep(0.5)  # brief wait; util.waitUntilComplete would be faster intraday
        spot = spot_tk.marketPrice() or spot_tk.last or spot_tk.close
    finally:
        if spot_tk.contract:
            ib.cancelMktData(spot_tk.contract)

    # ── build strike list: ±20 strikes around spot ───────────────────────────
    strikes_all = sorted(chain.strikes)
    if spot:
        # find index of strike closest to the underlying price
        try:
            spot_idx = min(range(len(strikes_all)),
                           key=lambda i: abs(strikes_all[i] - spot))
        except ValueError:      # strikes_all empty safeguard
            spot_idx = 0
        lower = max(0, spot_idx - 20)
        upper = min(len(strikes_all), spot_idx + 21)   # upper bound is exclusive
        strikes = strikes_all[lower:upper]
    else:
        # fallback: no underlying price – keep full chain
        strikes = strikes_all

    # ── sanity‑check strikes against what IB really lists for this expiry ──
    valid_strikes_set = set(chain.strikes)
    strikes = [s for s in strikes if s in valid_strikes_set]
    if len(strikes) < len(strikes_all):
        logger.debug("Filtered to %d valid strikes (from %d) to avoid 200‑errors",
                     len(strikes), len(strikes_all))

    # Build every C & P strike at that expiry,
    # keeping only contracts that IBKR recognises.
    contracts = []
    for strike in strikes:
        for right in ("C", "P"):
            opt = Option(symbol, expiry, strike, right,
                         exchange="SMART", currency="USD",
                         tradingClass=root_tc)
            try:
                det = ib.reqContractDetails(opt)
                if det and det[0].contract.conId:
                    contracts.append(det[0].contract)
            except Exception:
                continue  # skip bad ones

    if not contracts:
        raise RuntimeError("No valid option contracts found")

    # Request streaming market data (required for generic-tick 101)
    snapshots = []
    for c in contracts:
        snapshot = ib.reqMktData(
            c,
            "101,104,106",     # OI, modelGreeks, IV
            snapshot=False,    # streaming required for generic‑tick 101
            regulatorySnapshot=False,
        )
        snapshots.append((c, snapshot))
    _wait_for_snapshots(ib, snapshots)
    # Cancel just in case
    for _, snap in snapshots:
        ib.cancelMktData(snap.contract)

    rows = []
    ts = datetime.now(timezone.utc).isoformat()
    for con, tk in snapshots:
        rows.append({
            "timestamp": ts,
            "symbol": symbol,
            "expiry": expiry,
            "strike": con.strike,
            "right": con.right,
            "bid": tk.bid,
            "ask": tk.ask,
            "mid": np.nan if any(np.isnan([tk.bid, tk.ask])) else (tk.bid + tk.ask) / 2,
            "iv": _g(tk, "impliedVolatility"),
            "delta": _g(tk, "delta"),
            "gamma": _g(tk, "gamma"),
            "vega": _g(tk, "vega"),
            "theta": _g(tk, "theta"),
            "open_interest": _g(tk, "openInterest"),
        })

    df = pd.DataFrame(rows).sort_values(["right", "strike"]).reset_index(drop=True)
    return df


# ─────────────────────────── MAIN ──────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Option-chain snapshot exporter")
    parser.add_argument("--symbols", type=str,
                        help="Comma-separated list of tickers (overrides portfolio).")
    args = parser.parse_args()

    # ── connect ────────────────────────────────────────────
    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, IB_CID, timeout=10)  # Increased timeout
        ib.reqMarketDataType(4)          # fall‑back to delayed quotes after hours
    except Exception as exc:
        logger.error("IBKR connection failed: %s", exc)
        sys.exit(1)

    # ── decide which symbols to process ───────────────────
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        # prompt the user once
        raw = input("Symbols to snapshot (comma separated) — "
                    "leave empty to use full portfolio: ").strip()
        if raw:
            symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
        else:
            symbols = get_portfolio_tickers(ib)
            if not symbols:
                symbols = load_tickers_from_files()

    if not symbols:
        logger.error("No symbols to process — aborting.")
        sys.exit(1)

    logger.info("Symbols: %s", ", ".join(symbols))
    iterable = tqdm(symbols, desc="Option snapshots") if PROGRESS else symbols

    # ── expiry hint logic ───────────────────────────────
    portfolio_mode = not args.symbols and not raw
    expiry_hint = None
    if not portfolio_mode:
        expiry_hint = input("Desired option expiry (YYYYMMDD / YYYYMM / month name), "
                            "leave empty for automatic: ").strip()
        if not expiry_hint:
            expiry_hint = None

    # ── fetch and write CSVs ───────────────────────────────
    date_tag = datetime.utcnow().strftime("%Y%m%d")
    combined = []            # collect dfs when portfolio_mode
    for sym in iterable:
        try:
            df = snapshot_chain(ib, sym, expiry_hint)
            if df.empty:
                logger.warning("%s – no data", sym)
                continue
            if portfolio_mode:
                combined.append(df)
            else:
                out_path = os.path.join(OUTPUT_DIR,
                                        f"option_chain_{sym}_{date_tag}.csv")
                df.to_csv(out_path, index=False, quoting=csv.QUOTE_MINIMAL)
                logger.info("Saved %s (%d rows)", out_path, len(df))
        except Exception as e:
            logger.warning("%s – skipped: %s", sym, e)

    if portfolio_mode and combined:
        df_all = pd.concat(combined, ignore_index=True)
        out_path = os.path.join(OUTPUT_DIR,
                                f"option_chain_portfolio_{date_tag}.csv")
        df_all.to_csv(out_path, index=False, quoting=csv.QUOTE_MINIMAL)
        logger.info("Saved consolidated portfolio snapshot → %s (%d rows)",
                    out_path, len(df_all))

    ib.disconnect()


if __name__ == "__main__":
    main()
