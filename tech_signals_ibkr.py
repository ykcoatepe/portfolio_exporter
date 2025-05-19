#!/usr/bin/env python3
"""
tech_signals_ibkr.py — Pull live technical indicators via IBKR / TWS Gateway
----------------------------------------------------------------------------

Outputs: tech_signals.csv
Columns:
    timestamp · ticker · ADX · ATR · 20dma · 50dma · 200dma · IV_rank · RSI
    · beta_SPY · ADV30 · next_earnings · OI_near_ATM
"""

import os, sys, time, logging
from math import log, sqrt, erf
from datetime import datetime

# Additional import for yfinance fallback
import numpy as np
import pandas as pd
from ib_insync import IB, Stock, Option, util
import yfinance as yf
# Symbol → (Contract class, kwargs) for non‑stock underlyings
from ib_insync import Index, Future, ContFuture  # already imported IB, Stock, Option, util
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
PORTFOLIO_FILES = ["tickers_live.txt", "tickers.txt"]
DATE_TAG = datetime.utcnow().strftime("%Y%m%d")
# save to iCloud Drive Downloads
OUTPUT_DIR = "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_CSV = os.path.join(OUTPUT_DIR, f"tech_signals_{DATE_TAG}.csv")

HIST_DAYS       = 300          # enough for SMA200 / ADX
SPAN_PCT        = 0.05       # ±5 % strike window
ATM_DELTA_BAND  = 0.10         # |Δ| ≤ 0.10
RISK_FREE_RATE  = 0.01
DATA_DIR        = "iv_history"
os.makedirs(DATA_DIR, exist_ok=True)

IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7497, 1   # tweak if needed

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

# quiet ib_insync chatter
logging.getLogger("ib_insync.wrapper").setLevel(logging.WARNING)
logging.getLogger("ib_insync.client").setLevel(logging.WARNING)
logging.getLogger("ib_insync.ib").setLevel(logging.ERROR)

# ────────────────────── helpers ────────────────────────────
def _norm_cdf(x): return 0.5 * (1.0 + erf(x / sqrt(2)))
def _bs_delta(S, K, T, r, sigma, call=True):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    d1 = (log(S / K) + (r + 0.5*sigma**2)*T)/(sigma*sqrt(T))
    return _norm_cdf(d1) if call else _norm_cdf(d1) - 1.0

def load_tickers():
    p = next((f for f in PORTFOLIO_FILES if os.path.exists(f)), None)
    if not p:
        logging.error("Portfolio file not found; aborting.")
        sys.exit(1)
    with open(p) as f:
        return [l.strip().upper() for l in f if l.strip()]

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
ib.connect(IB_HOST, IB_PORT, clientId=IB_CID)

rows, tickers = [], load_tickers()
ts_now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

# pull SPY once for beta
spy = Stock("SPY", "SMART", "USD")
spy_bars = ib.reqHistoricalData(spy, "", f"{HIST_DAYS} D",
                                "1 day", "TRADES", useRTH=True)
spy_ret = pd.Series(dtype=float)
if spy_bars:
    _df = util.df(spy_bars)
    if not _df.empty:
        spy_ret = _df["close"].pct_change().dropna()

for tk in tickers:
    logging.info("▶ %s", tk)
    if tk == "MOVE":
        logging.info("Skipping option chain for MOVE index (no options).")
        continue
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

    df.set_index("date", inplace=True)
    c, h, l = df["close"], df["high"], df["low"]
    c_ff = c.ffill()   # forward‑fill so today’s partial bar isn’t NaN

    sma20  = float(c_ff.rolling(20,  min_periods=1).mean().iloc[-1])
    sma50  = float(c_ff.rolling(50,  min_periods=1).mean().iloc[-1])
    sma200 = float(c_ff.rolling(200, min_periods=1).mean().iloc[-1])
    delta = c_ff.diff()
    gain  = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss  = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    rsi14 = 100 - 100 / (1 + gain / (loss + 1e-9))
    tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean().iloc[-1]
    plus_dm = (h.diff()).where((h.diff()>l.diff().abs())&(h.diff()>0),0)
    minus_dm= (l.diff()).where((l.diff()>h.diff().abs())&(l.diff()>0),0)
    tr14 = tr.rolling(14).sum()
    pdi = 100*plus_dm.rolling(14).sum()/tr14
    mdi = 100*minus_dm.rolling(14).sum()/tr14
    adx14 = ((pdi-mdi).abs()/(pdi+mdi)*100).rolling(14).mean().iloc[-1]
    ADV30 = df["volume"].tail(30).mean()

    # -------------------------------- option chain section ------------------------------
    # Only run option‑chain logic for *stock or ETF underlyings*.
    # Anything with secType other than 'STK' (futures, indexes, cash, etc.)
    # is skipped to avoid 322 / 200 errors and hangs.
    if stk.secType != "STK":
        iv_now = oi_near = earn_dt = np.nan
    else:
        try:
            chains = ib.reqSecDefOptParams(tk, "", "STK", stk.conId)
            if not chains:
                raise Exception("No option‑chain data")

            expirations = sorted(chains[0].expirations)
            if not expirations:
                raise Exception("No expirations")

            today_d = datetime.utcnow().date()
            # Prefer the nearest expiry ≤ 7 days (weekly); else fallback to first Friday; else earliest
            expiry = next((e for e in expirations
                           if (datetime.strptime(e, "%Y%m%d").date() - today_d).days <= 7),
                      next((e for e in expirations
                           if datetime.strptime(e, "%Y%m%d").weekday() == 4),
                           expirations[0]))

            trading_classes = getattr(chains[0], "tradingClasses", [])
            root_tc = trading_classes[0] if trading_classes else tk

            strikes_full = sorted(chains[0].strikes)
            spot = c_ff.iloc[-1]

            # Keep only strikes within ±5 % of spot and snap to 0.50 increments
            strikes = []
            for s in strikes_full:
                if s <= 0 or abs(s - spot) > SPAN_PCT * spot:
                    continue
                s_snap = round(s * 2) / 2      # nearest 0.50 increment
                if abs(s_snap*2 - round(s_snap*2)) < 1e-4:   # ensure .00 or .50
                    strikes.append(s_snap)
            strikes = sorted(set(strikes), key=lambda x: abs(x - spot))[:12]   # 12 closest strikes

            # Build contracts; add tradingClass to improve recognition
            contracts = []
            for s in strikes:
                for r in ("C", "P"):
                    contracts.append(
                        Option(tk, expiry, s, r,
                               exchange="SMART", currency="USD", tradingClass=root_tc)
                    )

            # Qualify contracts; drop the ones that fail immediately
            qual = []
            for con in contracts:
                try:
                    ql = ib.qualifyContracts(con)
                    if ql and ql[0].conId:
                        qual.append(ql[0])
                except Exception:
                    continue
            if not qual:
                raise Exception("No valid contracts after qualification")

            # Request market data snapshots
            for con in qual:
                try:
                    # openInterest only arrives on streaming market data → snapshot must be False
                    ib.reqMktData(con, "101,106", False, False)   # 101=openInt,106=impVol
                except Exception:
                    continue    # silently skip rejects
            time.sleep(3.0)   # give snapshots time to populate
            # Cancel streaming to avoid dangling subscriptions
            for con in qual:
                ib.cancelMktData(con)
            # Allow IB gateway a brief breather to clear errors
            time.sleep(0.5)

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
            cal = yf.Ticker(tk).calendar
            if not cal.empty and 'Earnings Date' in cal.index:
                edm = cal.loc['Earnings Date'][0]
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

    time.sleep(0.25)

pd.DataFrame(rows).to_csv(OUTPUT_CSV,index=False)
logging.info("Saved %d rows → %s", len(rows), OUTPUT_CSV)
ib.disconnect()
