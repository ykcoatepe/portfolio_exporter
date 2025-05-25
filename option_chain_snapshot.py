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
"""

import argparse
import csv
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Sequence

import numpy as np
import pandas as pd
from ib_insync import IB, Option, Stock

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

    • exact YYYYMMDD → use if available
    • YYYYMM prefix → choose 3rd Friday of that month, else first expiry
    • month name/abbr (“july”) → same logic across any year
    • otherwise falls back to `choose_expiry`.
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


# ─────────── Black–Scholes fallback (for delayed feeds) ───────────
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_greeks(S, K, T, r, sigma, call=True):
    """
    Closed-form Black–Scholes Greeks (per contract).
    Vega per 1 % IV; theta per calendar-day.
    """
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0 or any(map(math.isnan, (S, K, T, sigma))):
        return dict(delta=np.nan, gamma=np.nan, vega=np.nan, theta=np.nan)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
    if call:
        delta = _norm_cdf(d1)
        theta = (-S * pdf * sigma / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * _norm_cdf(d2)) / 365.0
    else:
        delta = _norm_cdf(d1) - 1
        theta = (-S * pdf * sigma / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * _norm_cdf(-d2)) / 365.0
    gamma = pdf / (S * sigma * math.sqrt(T))
    vega = S * pdf * math.sqrt(T) / 100.0
    return dict(delta=delta, gamma=gamma, vega=vega, theta=theta)


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


def _wait_for_snapshots(ib: IB, snaps: list[tuple], timeout=8.0):
    """Wait until all tickers have a non-None timestamp or timeout."""
    end = time.time() + timeout
    while time.time() < end:
        if all(getattr(tk, "time", None) for _, tk in snaps):
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

    chain = chains[0]
    expiry = pick_expiry_with_hint(sorted(chain.expirations), expiry_hint)

    # trading class
    root_tc = (
        chain.tradingClasses[0]
        if getattr(chain, "tradingClasses", None)
        else getattr(chain, "tradingClass", symbol) or symbol
    )

    # ── spot price and ±20 strikes ──
    spot_tk = ib.reqMktData(stk, "", True, False)
    ib.sleep(0.5)
    spot = spot_tk.marketPrice() or spot_tk.last or spot_tk.close
    if spot_tk.contract:
        ib.cancelMktData(spot_tk.contract)

    strikes_all = sorted(chain.strikes)
    if spot:
        idx = min(range(len(strikes_all)), key=lambda i: abs(strikes_all[i] - spot))
        strikes = strikes_all[max(0, idx - 20) : min(len(strikes_all), idx + 21)]
    else:
        strikes = strikes_all

    # keep only valid strikes in case list came from previous expiry
    strikes = [s for s in strikes if s in chain.strikes]
    if not strikes:
        raise RuntimeError("No valid strike list")

    # build contracts
    contracts = []
    for strike in strikes:
        for right in ("C", "P"):
            opt = Option(symbol, expiry, strike, right, exchange="SMART", currency="USD", tradingClass=root_tc)
            try:
                det = ib.reqContractDetails(opt)
                if det and det[0].contract.conId:
                    contracts.append(det[0].contract)
            except Exception:
                continue
    if not contracts:
        raise RuntimeError("No valid option contracts found")

    # stream market data (need streaming for generic-tick 101)
    snapshots = [
        (
            c,
            ib.reqMktData(
                c,
                "101,104,106",  # OI, modelGreeks, IV
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

    # ── one-shot snapshot fallback for missing price / IV / OI ──
    for con, tk in snapshots:
        price_missing = ((tk.bid in (None, -1)) and (tk.last in (None, -1)))
        iv_missing = math.isnan(_g(tk, "impliedVolatility"))
        oi_missing = math.isnan(_g(tk, "openInterest"))
        if price_missing or iv_missing or oi_missing:
            snap = ib.reqMktData(con, "101,104,106", True, False)
            ib.sleep(0.30)
            for fld in ("bid", "ask", "last", "close", "impliedVolatility"):
                val = getattr(snap, fld, None)
                if val not in (None, -1):
                    setattr(tk, fld, val)
            if getattr(snap, "modelGreeks", None):
                tk.modelGreeks = snap.modelGreeks
            # Copy openInterest if present
            if getattr(snap, "openInterest", None) not in (None, -1):
                tk.openInterest = snap.openInterest
            ib.cancelMktData(snap.contract)

    # build rows
    ts = datetime.now(timezone.utc).isoformat()
    rows = []
    for con, tk in snapshots:
        iv_val = _g(tk, "impliedVolatility")
        delta_val = _g(tk, "delta")
        gamma_val = _g(tk, "gamma")
        vega_val = _g(tk, "vega")
        theta_val = _g(tk, "theta")

        # Black-Scholes fallback if still NaN
        if any(np.isnan(x) for x in (delta_val, gamma_val, vega_val, theta_val)):
            if spot and iv_val and not np.isnan(iv_val):
                exp_dt = datetime.strptime(expiry, "%Y%m%d").replace(tzinfo=timezone.utc)
                T = max((exp_dt - datetime.now(timezone.utc)).total_seconds() / (365 * 24 * 3600), 1 / (365 * 24))
                bs = _bs_greeks(spot, con.strike, T, 0.01, iv_val, con.right == "C")
                delta_val = bs["delta"] if np.isnan(delta_val) else delta_val
                gamma_val = bs["gamma"] if np.isnan(gamma_val) else gamma_val
                vega_val = bs["vega"] if np.isnan(vega_val) else vega_val
                theta_val = bs["theta"] if np.isnan(theta_val) else theta_val

        mid_price = (
            np.nan
            if any(np.isnan([tk.bid, tk.ask]))
            else (tk.bid + tk.ask) / 2
        )

        rows.append(
            {
                "timestamp": ts,
                "symbol": symbol,
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
                "open_interest": _g(tk, "openInterest"),
            }
        )

    return (
        pd.DataFrame(rows).sort_values(["right", "strike"]).reset_index(drop=True)
        if rows
        else pd.DataFrame()
    )


# ─────────────────────────── MAIN ──────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Option-chain snapshot exporter")
    parser.add_argument("--symbols", type=str, help="Comma-separated tickers (overrides portfolio).")
    args = parser.parse_args()

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

    # decide symbols
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        raw = None
    else:
        raw = input("Symbols to snapshot (comma separated) — leave empty for portfolio: ").strip()
        symbols = (
            [s.strip().upper() for s in raw.split(",") if s.strip()]
            if raw
            else get_portfolio_tickers(ib) or load_tickers_from_files()
        )

    if not symbols:
        logger.error("No symbols to process — aborting.")
        sys.exit(1)

    portfolio_mode = not args.symbols and not raw
    expiry_hint = None
    if not portfolio_mode:
        hint = input("Desired expiry (YYYYMMDD / YYYYMM / month name), leave empty for auto: ").strip()
        expiry_hint = hint or None

    logger.info("Symbols: %s", ", ".join(symbols))
    iterable = tqdm(symbols, desc="Option snapshots") if PROGRESS else symbols

    date_tag = datetime.utcnow().strftime("%Y%m%d")
    combined = []
    for sym in iterable:
        try:
            df = snapshot_chain(ib, sym, expiry_hint)
            if df.empty:
                logger.warning("%s – no data", sym)
                continue
            if portfolio_mode:
                combined.append(df)
            else:
                out_path = os.path.join(OUTPUT_DIR, f"option_chain_{sym}_{date_tag}.csv")
                df.to_csv(out_path, index=False, quoting=csv.QUOTE_MINIMAL, float_format="%.4f")
                logger.info("Saved %s (%d rows)", out_path, len(df))
        except Exception as e:
            logger.warning("%s – skipped: %s", sym, e)

    if portfolio_mode and combined:
        df_all = pd.concat(combined, ignore_index=True)
        out_path = os.path.join(OUTPUT_DIR, f"option_chain_portfolio_{date_tag}.csv")
        df_all.to_csv(out_path, index=False, quoting=csv.QUOTE_MINIMAL, float_format="%.4f")
        logger.info("Saved consolidated portfolio snapshot → %s (%d rows)", out_path, len(df_all))

    ib.disconnect()


if __name__ == "__main__":
    main()