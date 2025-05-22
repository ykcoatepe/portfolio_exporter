#!/usr/bin/env python3
"""
portfolio_greeks.py  –  Export per-position option Greeks and account-level totals

• Pulls current positions from the connected IBKR account.
• Requests market data snapshots for options to retrieve Greeks and IV.
  It uses short-lived streaming subscriptions to get fresh data.
• Computes *exposure* greeks → raw greek × contract multiplier × position size
  so that numbers reflect portfolio impact (e.g. Delta $ equivalent).
• Produces **two** CSV files in the same Downloads folder used by the other tools:
    1. portfolio_greeks_<YYYYMMDD>.csv          – one row per contract / underlying.
    2. portfolio_greeks_totals_<YYYYMMDD>.csv   – a single row with summed totals.

Usage
=====
$ python portfolio_greeks.py                       # full portfolio
$ python portfolio_greeks.py --symbols MSFT,QQQ    # restrict to subset
"""

import argparse
import csv
import logging
import math
import os
import sys
from datetime import datetime, timezone
from math import erf, log, sqrt
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from ib_insync import (Future, IB, Index, Option, Position, Stock, Ticker,
                       util)
from ib_insync.contract import Contract

try:
    from tqdm import tqdm
    PROGRESS = True
except ImportError:
    PROGRESS = False

# ───────────────────────── CONFIG ──────────────────────────
OUTPUT_DIR = (
    "/Users/yordamkocatepe/Library/Mobile Documents/"
    "com~apple~CloudDocs/Downloads"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7497, 11  # separate clientId from snapshots
LOG_FMT = "%(asctime)s %(levelname)s %(name)s %(message)s"

logging.basicConfig(level=logging.INFO, format=LOG_FMT)
logger = logging.getLogger(__name__)

# contract multipliers by secType (IB doesn't always fill this field)
DEFAULT_MULT = {
    "OPT": 100,
    "FOP": 50,   # common default – varies by product
    "FUT": 1,
    "STK": 1,
    "CASH": 100_000,   # treat FX as notional per lot
}

# tunables
TIMEOUT_SECONDS = 20      # seconds to wait for model‑Greeks before falling back
DEFAULT_SIGMA    = 0.40   # fallback IV if IB does not provide one

RISK_FREE_RATE = 0.01   # annualised risk-free rate for BS fallback
# ───────────────────── helpers ──────────────────────


def _multiplier(c: Contract) -> int:
    """Return contract multiplier with sensible fallbacks."""
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


# ────────────── Black–Scholes helpers ──────────────
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _bs_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    call: bool = True,
) -> Dict[str, float]:
    """
    Closed-form Black–Scholes Greeks (per contract).
    vega shown per 1 % IV; theta per calendar-day.
    """
    if (
        S <= 0
        or K <= 0
        or T <= 0
        or sigma <= 0
        or math.isnan(S)
        or math.isnan(K)
        or math.isnan(T)
        or math.isnan(sigma)
    ):
        return dict(delta=np.nan, gamma=np.nan, vega=np.nan, theta=np.nan)

    d1 = (log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    pdf_d1 = math.exp(-0.5 * d1**2) / sqrt(2 * math.pi)

    if call:
        delta = _norm_cdf(d1)
        theta = (
            -S * pdf_d1 * sigma / (2 * sqrt(T))
            - r * K * math.exp(-r * T) * _norm_cdf(d2)
        ) / 365.0
    else:
        delta = _norm_cdf(d1) - 1.0
        theta = (
            -S * pdf_d1 * sigma / (2 * sqrt(T))
            + r * K * math.exp(-r * T) * _norm_cdf(-d2)
        ) / 365.0

    gamma = pdf_d1 / (S * sigma * sqrt(T))
    vega = S * pdf_d1 * sqrt(T) / 100.0

    return dict(delta=delta, gamma=gamma, vega=vega, theta=theta)


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
    Return list of (Position, Ticker) for all option/FOP positions with live data.
    """
    positions = [p for p in ib.portfolio() if p.position != 0]
    positions = [p for p in positions if p.contract.secType in {"OPT", "FOP"}]
    if not positions:
        return []

    logger.info(f"Found {len(positions)} option/FOP positions. Requesting market data...")

    tickers: List[Tuple[Position, Ticker]] = []
    for pos in positions:
        qc = ib.qualifyContracts(pos.contract)
        if not qc:
            logger.warning(f"Could not qualify {pos.contract.localSymbol}. Skipping.")
            continue
        c = qc[0]
        if not c.exchange:
            c.exchange = "SMART"

        # 100 = open interest, 106 = option implied‑volatility
        tk = ib.reqMktData(
            c,
            genericTickList="100,106",
            snapshot=False,
            regulatorySnapshot=False
        )
        tickers.append((pos, tk))

    # wait until all tickers have at least delta, or timeout
    timeout_seconds = TIMEOUT_SECONDS
    deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
    while datetime.now(timezone.utc).timestamp() < deadline:
        ib.sleep(0.25)
        if all(_has_any_greeks_populated(t) for _, t in tickers):
            logger.info("All tickers have received Greeks.")
            break
    else:
        logger.warning("Timeout reached. Not all tickers received full Greek data.")
        for pos, tk in tickers:
            if not _has_any_greeks_populated(tk):
                logger.warning(f"{pos.contract.localSymbol} still missing Greeks.")

    return tickers


# ─────────────────────────── MAIN ──────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio Greeks exporter")
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated tickers to include (filters positions).",
    )
    args = parser.parse_args()

    ib = IB()
    try:
        logger.info(f"Connecting to IBKR on {IB_HOST}:{IB_PORT} with CID {IB_CID} …")
        ib.connect(IB_HOST, IB_PORT, IB_CID, timeout=10)
    except Exception as exc:
        logger.error(f"IBKR connection failed: {exc}", exc_info=True)
        sys.exit(1)

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

    ts_utc = datetime.now(timezone.utc)
    ts_iso = ts_utc.isoformat()
    rows: List[Dict[str, Any]] = []

    iterable = tqdm(pkgs, desc="Processing portfolio greeks") if PROGRESS else pkgs
    for pos, tk in iterable:
        c: Contract = pos.contract
        mult = _multiplier(c)
        qty = pos.position

        # pick first greeks set
        src = next(
            (
                getattr(tk, name)
                for name in ("modelGreeks", "lastGreeks", "bidGreeks", "askGreeks")
                if getattr(tk, name, None) and getattr(getattr(tk, name), "delta") is not None
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
                    if c.secType == "OPT":
                        under = Stock(c.symbol, "SMART", "USD")
                    elif c.secType == "FOP":
                        under = Future(c.symbol, "", exchange="GLOBEX")
                    else:
                        under = None
                    if under:
                        ib.qualifyContracts(under)
                        snap = ib.reqMktData(under, "", True, False)
                        ib.sleep(1.0)
                        S = snap.midpoint() or snap.last or snap.close or np.nan
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
                    exp_naive.year, exp_naive.month, exp_naive.day, 23, 59, 59, tzinfo=timezone.utc
                )
                T = max((exp - ts_utc).total_seconds() / (365 * 24 * 3600), 1 / (365 * 24 * 3600))
            except Exception:
                pass

            sigma = iv_from_greeks
            if math.isnan(sigma) or sigma <= 0:
                sigma = getattr(tk, "impliedVolatility", np.nan)
            if math.isnan(sigma) or sigma <= 0:
                sigma = DEFAULT_SIGMA

            if not any(math.isnan(x) for x in (S, K, T, sigma)):
                bs = _bs_greeks(S, K, T, RISK_FREE_RATE, sigma, c.right == "C")
                for k in greeks:
                    if math.isnan(greeks[k]):
                        greeks[k] = bs[k]

        if all(math.isnan(v) for v in greeks.values()):
            continue

        option_price = tk.marketPrice or tk.last or tk.close

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
                "open_interest": getattr(tk, "openInterest", np.nan),
                "iv": iv_from_greeks if not math.isnan(iv_from_greeks) else tk.impliedVolatility,
                **greeks,
                "delta_exposure": greeks["delta"] * qty * mult,
                "gamma_exposure": greeks["gamma"] * qty * mult,
                "vega_exposure": greeks["vega"] * qty * mult,
                "theta_exposure": greeks["theta"] * qty * mult,
            }
        )

    # now that all fields are captured we can drop the live subscriptions
    for _, tk in pkgs:
        ib.cancelMktData(tk.contract)
    logger.info("Market data streams cancelled.")

    if not rows:
        logger.warning("No rows produced – nothing to write.")
        ib.disconnect()
        sys.exit(0)

    df = pd.DataFrame(rows)
    totals = df[["delta_exposure", "gamma_exposure", "vega_exposure", "theta_exposure"]].sum().to_frame().T
    totals.insert(0, "timestamp", ts_iso)

    date_tag = ts_utc.strftime("%Y%m%d")
    fn_pos = os.path.join(OUTPUT_DIR, f"portfolio_greeks_{date_tag}.csv")
    fn_tot = os.path.join(OUTPUT_DIR, f"portfolio_greeks_totals_{date_tag}.csv")

    df.to_csv(fn_pos, index=False, float_format="%.6f")
    totals.to_csv(fn_tot, index=False, float_format="%.2f")
    logger.info(f"Saved {len(df)} rows  → {fn_pos}")
    logger.info(f"Saved totals         → {fn_tot}")

    ib.disconnect()


if __name__ == "__main__":
    main()