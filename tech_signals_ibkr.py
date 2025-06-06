#!/usr/bin/env python3
"""
tech_signals_ibkr.py — Pull live technical indicators via IBKR / TWS Gateway
----------------------------------------------------------------------------

Outputs: tech_signals_YYYYMMDD_HHMM.csv
Columns:
    timestamp · ticker · ADX · ATR · 20dma · 50dma · 200dma · IV_rank · RSI
    · beta_SPY · ADV30 · next_earnings · OI_near_ATM
"""

import logging
import os
import sys
from math import erf, log, sqrt
from datetime import datetime

# Additional import for yfinance fallback
import numpy as np
import pandas as pd
from ib_insync import IB, Stock, Option, util
# Additional import for yfinance fallback
import yfinance as yf
# optional progress bar
try:
    from tqdm import tqdm
    PROGRESS = True
except ImportError:
    PROGRESS = False
# Symbol → (Contract class, kwargs) for non‑stock underlyings
from ib_insync import Index, Future  # already imported IB, Stock, Option, util
SYMBOL_MAP = {
    "VIX":  (Index,  dict(symbol="VIX",  exchange="CBOE")),
    "VVIX": (Index,  dict(symbol="VVIX", exchange="CBOE")),
    "^TNX": (Index,  dict(symbol="TNX",  exchange="CBOE")),
    "^TYX": (Index,  dict(symbol="TYX",  exchange="CBOE")),
    # Futures entries in SYMBOL_MAP are not used for contract selection anymore
    "GC=F": (Future, dict(symbol="GC", lastTradeDateOrContractMonth="", exchange="COMEX")),
    "SI=F": (Future, dict(symbol="SI", lastTradeDateOrContractMonth="", exchange="COMEX")),
    "CL=F": (Future, dict(symbol="CL", lastTradeDateOrContractMonth="", exchange="NYMEX")),
    "HG=F": (Future, dict(symbol="HG", lastTradeDateOrContractMonth="", exchange="COMEX")),
    "NG=F": (Future, dict(symbol="NG", lastTradeDateOrContractMonth="", exchange="NYMEX")),
}

# Map yfinance-style futures tickers to (root symbol, exchange)
FUTURE_ROOTS = {
    "GC=F": ("GC", "COMEX"),
    "SI=F": ("SI", "COMEX"),
    "CL=F": ("CL", "NYMEX"),
    "HG=F": ("HG", "COMEX"),
    "NG=F": ("NG", "NYMEX"),
}

# ───────────────────────── CONFIG ──────────────────────────
# Include time in file names to avoid overwriting when run multiple times a day
PORTFOLIO_FILES = ["tickers_live.txt", "tickers.txt"]
DATE_TAG = datetime.utcnow().strftime("%Y%m%d")
TIME_TAG = datetime.utcnow().strftime("%H%M")
# save to iCloud Drive Downloads
OUTPUT_DIR = "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_CSV = os.path.join(
    OUTPUT_DIR, f"tech_signals_{DATE_TAG}_{TIME_TAG}.csv"
)

HIST_DAYS       = 300          # enough for SMA200 / ADX
SPAN_PCT        = 0.05       # ±5 % strike window
N_ATM_STRIKES   = 4           # number of strikes on each side of ATM to keep (reduced for speed)
ATM_DELTA_BAND  = 0.10         # |Δ| ≤ 0.10
RISK_FREE_RATE  = 0.01
DATA_DIR        = "iv_history"
os.makedirs(DATA_DIR, exist_ok=True)

IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7497, 1   # tweak if needed

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

# quiet ib_insync chatter
logging.getLogger("ib_insync.wrapper").setLevel(logging.CRITICAL)
logging.getLogger("ib_insync.client").setLevel(logging.CRITICAL)
logging.getLogger("ib_insync.ib").setLevel(logging.CRITICAL)

# ────────────────────── helpers ────────────────────────────
def _norm_cdf(x):
    return 0.5 * (1.0 + erf(x / sqrt(2)))


def _bs_delta(S, K, T, r, sigma, call=True):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    return _norm_cdf(d1) if call else _norm_cdf(d1) - 1.0

def load_tickers():
    p = next((f for f in PORTFOLIO_FILES if os.path.exists(f)), None)
    if not p:
        logging.error("Portfolio file not found; aborting.")
        sys.exit(1)
    with open(p) as f:
        return [line.strip().upper() for line in f if line.strip()]

# Helper to robustly parse IBKR lastTradeDateOrContractMonth and fetch nearest active future
def _parse_ib_month(dt_str: str) -> datetime:
    """
    IB future strings are either YYYYMM or YYYYMMDD.
    Return a datetime representing the first day of that month/contract.
    """
    try:
        if len(dt_str) == 6:
            return datetime.strptime(dt_str, "%Y%m")
        elif len(dt_str) == 8:
            return datetime.strptime(dt_str, "%Y%m%d")
    except ValueError:
        pass
    # unknown format → far past so it's considered expired
    return datetime(1900, 1, 1)

# ──────────────────────────── Option expiry validation ─────────────────────────────
def _first_valid_expiry(symbol: str, expirations: list[str], spot: float,
                        root_tc: str) -> str:
    """
    Return the first expiry whose chain has a *valid* ATM contract.
    Falls back to earliest expiry if none validate.
    """
    for exp in sorted(expirations, key=lambda d: pd.to_datetime(d)):
        atm = round(spot)  # simple ATM guess, refined later
        try:
            test = Option(symbol, exp, atm, "C",
                          exchange="SMART", currency="USD",
                          tradingClass=root_tc)
            det = ib.reqContractDetails(test)
            if det and det[0].contract.conId:
                return exp
        except Exception:
            continue
    return expirations[0]  # last‑ditch fallback

def front_future(root: str, exch: str) -> Future:
    """Return the nearest non‑expired future contract for root/exchange."""
    details = ib.reqContractDetails(Future(root, exchange=exch))
    if not details:
        raise ValueError("no contract details")
    # sort by maturity and return first future that hasn't expired
    for det in sorted(details, key=lambda d: _parse_ib_month(d.contract.lastTradeDateOrContractMonth)):
        dt = _parse_ib_month(det.contract.lastTradeDateOrContractMonth)
        if dt > datetime.utcnow():
            return det.contract
    # fallback to first detail if all expired
    return details[0].contract

# ────────────────────── connect IB ─────────────────────────
ib = IB()
# Suppress repetitive "No security definition" errors (code 200)
def _quiet_error_handler(reqId, errorCode, errorString, contract):
    if errorCode == 200:
        return  # silently ignore
    print(f"IB ERROR {errorCode}: {errorString}")
ib.errorEvent += _quiet_error_handler
try:
    ib.connect(IB_HOST, IB_PORT, clientId=IB_CID)
    USE_IB = True
except Exception:
    logging.warning("IBKR Gateway not reachable – using yfinance only.")
    USE_IB = False

rows, tickers = [], load_tickers()
ts_now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

# pull SPY once for beta
if USE_IB:
    spy = Stock("SPY", "SMART", "USD")
    spy_bars = ib.reqHistoricalData(spy, "", f"{HIST_DAYS} D",
                                    "1 day", "TRADES", useRTH=True)
    spy_ret = pd.Series(dtype=float)
    if spy_bars:
        _df = util.df(spy_bars)
        if not _df.empty:
            # Ensure we have a proper datetime index
            if "date" in _df.columns:
                _df.set_index("date", inplace=True)
            _df.index = pd.to_datetime(_df.index).tz_localize(None)
            spy_ret = _df["close"].pct_change().dropna()
else:
    try:
        spy_df = yf.download("SPY", period=f"{HIST_DAYS}d", interval="1d", progress=False)
        spy_df.rename(columns=str.lower, inplace=True)
        spy_df.index = pd.to_datetime(spy_df.index).tz_localize(None)
        spy_ret = spy_df["close"].pct_change().dropna() if not spy_df.empty else pd.Series(dtype=float)
    except Exception as e:
        logging.warning("yfinance hist error SPY: %s", e)
        spy_ret = pd.Series(dtype=float)

# If IB was used but spy_ret is still empty, fallback to yfinance
if spy_ret.empty:
    try:
        spy_df = yf.download("SPY", period=f"{HIST_DAYS}d", interval="1d", progress=False)
        if not spy_df.empty:
            spy_df.rename(columns=str.lower, inplace=True)
            spy_ret = spy_df["close"].pct_change().dropna()
    except Exception as e:
        logging.warning("secondary yfinance SPY error: %s", e)

if not spy_ret.empty:
    # drop timezone info so date intersections succeed
    spy_ret.index = pd.to_datetime(spy_ret.index).tz_localize(None)

iterable = tqdm(tickers, desc="tech signals") if PROGRESS else tickers
for tk in iterable:
    logging.info("▶ %s", tk)
    if tk == "MOVE":
        logging.info("Skipping option chain for MOVE index (no options).")
        continue

    if USE_IB:
        # ----- contract selection -----
        if tk in FUTURE_ROOTS:
            root, exch = FUTURE_ROOTS[tk]
            try:
                stk = front_future(root, exch)
            except Exception as e:
                logging.warning("Front future lookup failed for %s: %s", tk, e)
                continue
        elif tk in SYMBOL_MAP:
            cls, kw = SYMBOL_MAP[tk]
            stk = cls(**kw)
        else:
            stk = Stock(tk, "SMART", "USD")
        ib.qualifyContracts(stk)
        if not stk.conId:
            logging.warning("Could not qualify %s – skipping", tk)
            continue

        bar_type = "TRADES"
        if isinstance(stk, Index):
            bar_type = "MIDPOINT"   # indices don’t have prints
        if tk in {"VIX", "VVIX", "^TNX", "^TYX"}:
            bar_type = "TRADES"

        try:
            bars = ib.reqHistoricalData(stk, "", f"{HIST_DAYS} D",
                                        "1 day", bar_type, useRTH=True)
            df = util.df(bars) if bars else pd.DataFrame()
        except Exception as e:
            logging.warning("IB hist error %s: %s", tk, e)
            df = pd.DataFrame()

        # If IB failed, try yfinance
        if df.empty:
            try:
                yf_df = yf.download(tk, period=f"{HIST_DAYS}d", interval="1d", progress=False)
                yf_df.rename(columns=str.lower, inplace=True)  # align column names
                yf_df.reset_index(inplace=True)
                yf_df.rename(columns={"date": "date"}, inplace=True)
                df = yf_df
                logging.info("Used yfinance bars for %s", tk)
            except Exception as e:
                logging.warning("yfinance hist error %s: %s", tk, e)
                continue
    else:
        try:
            yf_df = yf.download(tk, period=f"{HIST_DAYS}d", interval="1d", progress=False)
            yf_df.rename(columns=str.lower, inplace=True)
            yf_df.reset_index(inplace=True)
            yf_df.rename(columns={"date": "date"}, inplace=True)
            df = yf_df
        except Exception as e:
            logging.warning("yfinance hist error %s: %s", tk, e)
            continue
        stk = None
        iv_now = oi_near = earn_dt = np.nan

    df.set_index("date", inplace=True)
    # drop timezone info so date intersections succeed
    df.index = pd.to_datetime(df.index).tz_localize(None)
    c, h, low = df["close"], df["high"], df["low"]
    c_ff = c.ffill()   # forward‑fill so today’s partial bar isn’t NaN

    sma20  = float(c_ff.rolling(20,  min_periods=1).mean().iloc[-1])
    sma50  = float(c_ff.rolling(50,  min_periods=1).mean().iloc[-1])
    sma200 = float(c_ff.rolling(200, min_periods=1).mean().iloc[-1])
    delta = c_ff.diff()
    gain  = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss  = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    rsi14 = 100 - 100 / (1 + gain / (loss + 1e-9))
    tr = pd.concat([h-low, (h-c.shift()).abs(), (low-c.shift()).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean().iloc[-1]
    plus_dm = (h.diff()).where((h.diff() > low.diff().abs()) & (h.diff() > 0), 0)
    minus_dm = (low.diff()).where((low.diff() > h.diff().abs()) & (low.diff() > 0), 0)
    tr14 = tr.rolling(14).sum()
    pdi = 100*plus_dm.rolling(14).sum()/tr14
    mdi = 100*minus_dm.rolling(14).sum()/tr14
    adx14 = ((pdi-mdi).abs()/(pdi+mdi)*100).rolling(14).mean().iloc[-1]
    ADV30 = df["volume"].tail(30).mean()

    # -------------------------------- option chain section ------------------------------
    # Only run option‑chain logic for *stock or ETF underlyings*.
    # Anything with secType other than 'STK' (futures, indexes, cash, etc.)
    # is skipped to avoid 322 / 200 errors and hangs.
    if USE_IB and stk is not None and stk.secType == "STK":
        try:
            chains = ib.reqSecDefOptParams(tk, "", "STK", stk.conId)
            if not chains:
                raise Exception("No option‑chain data")

            expirations = sorted(chains[0].expirations)
            if not expirations:
                raise Exception("No expirations")

            # Pick the first expiry that actually has a valid ATM contract
            trading_classes = getattr(chains[0], "tradingClasses", [])
            root_tc = trading_classes[0] if trading_classes else tk
            expiry = _first_valid_expiry(tk, expirations, c_ff.iloc[-1], root_tc)
            logging.info("Selected validated expiry %s for %s", expiry, tk)

            # --- keep ±N_ATM_STRIKES strikes around the ATM strike ---
            strikes_full = sorted(chains[0].strikes)
            spot = c_ff.iloc[-1]

            # determine exchange tick‐spacing (smallest positive gap)
            if len(strikes_full) >= 2:
                diffs = np.diff(strikes_full)
                tick = min(d for d in diffs if d > 0)
            else:
                tick = 0.5  # sensible fallback if list is tiny

            # nearest tradable strike to spot
            atm = round(spot / tick) * tick

            # Generate symmetric ladder around ATM
            candidate_strikes = [round(atm + i * tick, 2)
                                 for i in range(-N_ATM_STRIKES,
                                                N_ATM_STRIKES + 1)]

            # Retain only strikes IB actually lists
            strikes = [s for s in candidate_strikes if s in strikes_full]

            if not strikes:
                raise Exception("No candidate strikes found in chain")

            # Build contracts only for strikes that actually exist *at this expiry*.
            # We query IBKR for each candidate strike/right and keep only those that
            # return at least one ContractDetail – this eliminates “No security definition” (Error 200).
            contracts = []
            for s in strikes:
                s_float = float(s)           # ensure pure Python float
                for r in ("C", "P"):
                    opt = Option(tk, expiry, s_float, r,
                                 exchange="SMART", currency="USD")   # let IB auto‑select tradingClass
                    try:
                        det = ib.reqContractDetails(opt)
                        if det and det[0].contract.conId:
                            contracts.append(det[0].contract)
                    except Exception:
                        # skip strikes that IBKR does not recognise for this expiry
                        continue

            if not contracts:
                raise Exception("No valid option contracts at selected expiry")

            # Already qualified via reqContractDetails
            qual = contracts

            # Request market data snapshots
            for con in qual:
                try:
                    # openInterest only arrives on streaming market data → snapshot must be False
                    ib.reqMktData(con, "101,106", False, False)   # 101=openInt,106=impVol
                except Exception:
                    continue    # silently skip rejects
            ib.sleep(1.0)     # give snapshots ~1 s to populate while allowing the event loop to run
            # Cancel streaming to avoid dangling subscriptions
            for con in qual:
                ib.cancelMktData(con)
            # Allow IB gateway a brief breather to clear errors
            ib.sleep(0.1)

            # collect IV & OI
            iv_now = np.nan
            min_diff = 1e9
            T = max((datetime.strptime(expiry, "%Y%m%d") - datetime.utcnow()).days, 1) / 365
            oi_sum = 0
            for con in qual:
                tk_data = ib.ticker(con)
                iv_ = getattr(tk_data, "impliedVolatility", None)
                oi_ = getattr(tk_data, "openInterest", None)
                if iv_ is None or oi_ is None:
                    continue
                diff = abs(con.strike - spot)
                if con.right == "C" and diff < min_diff:
                    min_diff, iv_now = diff, iv_
                delta = _bs_delta(spot, con.strike, T, RISK_FREE_RATE,
                                  iv_, con.right == "C")
                if abs(delta) <= ATM_DELTA_BAND:
                    oi_sum += oi_
            oi_near = oi_sum

            # earnings date  – skipped to avoid News‑feed permission errors
            earn_dt = np.nan

        except Exception as e:
            logging.warning("Chain/OI/IV fail for %s: %s", tk, e)
            # iv_now, oi_near, earn_dt remain NaN

        # ---------- yfinance fallback for OI / IV ----------
        if (np.isnan(oi_near) or oi_near == 0 or np.isnan(iv_now)) and stk is not None:
            try:
                yft = yf.Ticker(tk)
                # pick the expiry that is nearest in time
                if yft.options:
                    yf_expiry = min(
                        yft.options,
                        key=lambda d: abs((pd.to_datetime(d) - pd.to_datetime('today')).days)
                    )
                    oc = yft.option_chain(yf_expiry)

                    spot = c_ff.iloc[-1]

                    def _near(df):
                        return df.loc[(df["strike"] - spot).abs() / spot <= SPAN_PCT]

                    calls, puts = _near(oc.calls), _near(oc.puts)

                    if (np.isnan(oi_near) or oi_near == 0) and (not calls.empty or not puts.empty):
                        oi_near = calls["openInterest"].fillna(0).sum() + puts["openInterest"].fillna(0).sum()

                    # If IV is still missing, grab the ATM call IV from yfinance
                    if np.isnan(iv_now) and not calls.empty:
                        iv_now = calls.loc[(calls["strike"] - spot).abs().idxmin(), "impliedVolatility"]
            except Exception as e:
                logging.debug("yfinance option fallback error for %s: %s", tk, e)
    else:
        iv_now = oi_near = earn_dt = np.nan

    # IV rank
    fn = os.path.join(DATA_DIR,f"{tk}.csv")
    if not np.isnan(iv_now):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        pd.DataFrame([[today, iv_now]],
                     columns=["date","iv"]).to_csv(fn, mode="a",
                     header=not os.path.exists(fn), index=False)
    iv_hist = pd.read_csv(fn).drop_duplicates("date").tail(252)["iv"] \
             if os.path.exists(fn) else pd.Series()
    iv_rank = np.nan if iv_hist.empty or iv_hist.max()==iv_hist.min() \
              else (iv_now-iv_hist.min())/(iv_hist.max()-iv_hist.min())*100

    # --- beta vs SPY (align on common dates) ---
    beta = np.nan
    if not spy_ret.empty:
        ret = c_ff.pct_change().dropna()
        common = spy_ret.index.intersection(ret.index)
        if len(common) > 10:            # need some overlap
            beta = np.cov(ret.loc[common], spy_ret.loc[common])[0, 1] / spy_ret.loc[common].var()

    # Fallback: pull next earnings date from yfinance if still NaN
    if earn_dt is np.nan or pd.isna(earn_dt):
        try:
            ed_df = yf.Ticker(tk).get_earnings_dates(limit=1)
            if not ed_df.empty:
                earn_dt = pd.to_datetime(ed_df["Earnings Date"].iloc[0]).date().isoformat()
        except Exception:
            # final fallback: use calendar attribute if available
            try:
                cal = yf.Ticker(tk).calendar
                if not cal.empty and "Earnings Date" in cal.index:
                    edm = cal.loc["Earnings Date"][0]
                    if not pd.isna(edm):
                        earn_dt = pd.to_datetime(edm).date().isoformat()
            except Exception:
                pass

    rows.append(dict(timestamp=ts_now, ticker=tk,
                     ADX=adx14, ATR=atr14,
                     _20dma=sma20, _50dma=sma50, _200dma=sma200,
                     IV_rank=iv_rank, RSI=rsi14,
                     beta_SPY=beta, ADV30=ADV30,
                     next_earnings=earn_dt, OI_near_ATM=oi_near))

    ib.sleep(0.05)

pd.DataFrame(rows).to_csv(OUTPUT_CSV,index=False)
logging.info("Saved %d rows → %s", len(rows), OUTPUT_CSV)
if USE_IB:
    ib.disconnect()
