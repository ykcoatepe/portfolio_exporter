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
from datetime import datetime, timezone
from typing import List, Sequence

import numpy as np
import pandas as pd
from ib_insync import IB, Stock, Option, util

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


def snapshot_chain(ib: IB, symbol: str) -> pd.DataFrame:
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
    expiry = choose_expiry(sorted(chain.expirations))

    # Build every C & P strike at that expiry,
    # keeping only contracts that IBKR recognises.
    contracts = []
    for strike in chain.strikes:
        for right in ("C", "P"):
            opt = Option(symbol, expiry, strike, right,
                         exchange="SMART", currency="USD",
                         tradingClass=chain.tradingClasses[0])
            try:
                det = ib.reqContractDetails(opt)
                if det and det[0].contract.conId:
                    contracts.append(det[0].contract)
            except Exception:
                continue  # skip bad ones

    if not contracts:
        raise RuntimeError("No valid option contracts found")

    # Request regulatory snapshots (one shot – non-streaming)
    snapshots = []
    for c in contracts:
        snapshot = ib.reqMktData(c, "101,106,100,101,104",  # OI=101, IV=106, greeks=100-104
                                 snapshot=True, regulatorySnapshot=True)
        snapshots.append((c, snapshot))
    ib.sleep(2.5)  # wait for all snapshots
    # Cancel just in case (should be auto-cancelled for snapshots)
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
            "iv": tk.impliedVolatility,
            "delta": tk.delta,
            "gamma": tk.gamma,
            "vega": tk.vega,
            "theta": tk.theta,
            "open_interest": tk.openInterest,
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
        ib.connect(IB_HOST, IB_PORT, IB_CID, timeout=5)
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

    # ── fetch and write CSVs ───────────────────────────────
    date_tag = datetime.utcnow().strftime("%Y%m%d")
    for sym in symbols:
        try:
            df = snapshot_chain(ib, sym)
            out_path = os.path.join(OUTPUT_DIR,
                                    f"option_chain_{sym}_{date_tag}.csv")
            df.to_csv(out_path, index=False, quoting=csv.QUOTE_MINIMAL)
            logger.info("Saved %s (%d rows)", out_path, len(df))
        except Exception as e:
            logger.warning("%s – skipped: %s", sym, e)

    ib.disconnect()


if __name__ == "__main__":
    main()