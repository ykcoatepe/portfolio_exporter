
'''
"""
analysis.py - Portfolio and market analysis functions.
"""
'''
"""
analysis.py - Portfolio and market analysis functions.
"""
import logging
import time
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import os

import numpy as np
import pandas as pd
import yfinance as yf
from ib_insync import IB, Option, Stock, Ticker, Index, Future, util

from utils.bs import bs_greeks, norm_cdf, _bs_delta
from utils.ib import _parse_ib_month, _first_valid_expiry, front_future

log = logging.getLogger(__name__)

def get_historical_prices(tickers, days_back=60) -> pd.DataFrame:
    """
    Batch-fetch OHLCV data for tickers over last `days_back` days with daily interval.
    Raises ValueError if ticker list is empty.
    Returns DataFrame with columns:
    ["date","ticker","open","high","low","close","adj_close","volume"]
    """
    if not tickers:
        raise ValueError("No data fetched for any ticker.")
    data = yf.download(
        tickers=tickers,
        period=f"{days_back}d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
    )
    columns = ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]
    if data.empty:
        return pd.DataFrame(columns=columns)
    dfs = []
    if isinstance(data.columns, pd.MultiIndex):
        for ticker in tickers:
            if ticker in data:
                df_t = data[ticker].reset_index()
                df_t["Ticker"] = ticker
                dfs.append(df_t)
    else:
        df_t = data.reset_index()
        df_t["Ticker"] = tickers[0]
        dfs.append(df_t)
    result = pd.concat(dfs, ignore_index=True)
    # Rename columns and enforce types
    result = result.rename(
        columns={
            "Date": "date",
            "Ticker": "ticker",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    result["date"] = result["date"].dt.strftime("%Y-%m-%d")
    result["volume"] = result["volume"].fillna(0).astype(int)
    return result[columns]

def get_greeks(ib: IB) -> pd.DataFrame:
    """
    Fetches option positions and their greeks.
    """
    positions = [p for p in ib.portfolio() if p.contract.secType == 'OPT']
    if not positions:
        return pd.DataFrame()

    # Request streaming data for greeks
    tickers = [ib.reqMktData(p.contract, "106", snapshot=False, regulatorySnapshot=False) for p in positions]
    log.info(f"Waiting for greeks for {len(tickers)} option positions...")
    ib.sleep(2.5)  # Allow time for streaming greeks to arrive

    rows = []
    for p, t in zip(positions, tickers):
        greeks = t.modelGreeks
        if greeks:
            rows.append({
                "symbol": p.contract.symbol,
                "expiry": p.contract.lastTradeDateOrContractMonth,
                "strike": p.contract.strike,
                "right": p.contract.right,
                "position": p.position,
                "iv": greeks.impliedVol,
                "delta": greeks.delta,
                "gamma": greeks.gamma,
                "vega": greeks.vega,
                "theta": greeks.theta,
                "underlying_price": greeks.undPrice,
            })
    
    # Clean up subscriptions
    for t in tickers:
        ib.cancelMktData(t.contract)

    return pd.DataFrame(rows)

def get_option_chain(ib: IB, symbol: str) -> pd.DataFrame:
    """
    Fetches the option chain for a given symbol.
    """
    stk = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(stk)
    
    chains = ib.reqSecDefOptParams(symbol, "", "STK", stk.conId)
    if not chains:
        log.warning(f"No option chain definitions found for {symbol}")
        return pd.DataFrame()

    # Heuristic: find the chain with the most strikes (usually the primary)
    chain = max(chains, key=lambda c: len(c.strikes))
    
    # Select a near-term expiry (e.g., within 45 days)
    expirations = sorted([exp for exp in chain.expirations if (pd.to_datetime(exp) - pd.Timestamp.now()).days < 45])
    if not expirations:
        log.warning(f"No near-term expirations found for {symbol}")
        return pd.DataFrame()
    expiry = expirations[0]

    # Filter strikes around the money
    spot_price = ib.reqMktData(stk, "", snapshot=True, regulatorySnapshot=False).marketPrice()
    ib.sleep(0.5)
    if pd.isna(spot_price):
        log.warning(f"Could not get spot price for {symbol}, using all strikes.")
        strikes = chain.strikes
    else:
        strikes = sorted([s for s in chain.strikes if abs(s - spot_price) / spot_price < 0.15]) # 15% moneyness

    contracts = [
        Option(symbol, expiry, strike, right, chain.exchange)
        for strike in strikes
        for right in ["C", "P"]
    ]
    ib.qualifyContracts(*contracts)
    
    tickers = [ib.reqMktData(c, "", snapshot=True, regulatorySnapshot=False) for c in contracts]
    log.info(f"Fetching option chain for {symbol} with {len(tickers)} contracts...")
    ib.sleep(2)

    rows = []
    for t in tickers:
        rows.append({
            "symbol": t.contract.symbol,
            "expiry": t.contract.lastTradeDateOrContractMonth,
            "strike": t.contract.strike,
            "right": t.contract.right,
            "last": t.last,
            "bid": t.bid,
            "ask": t.ask,
            "volume": t.volume,
            "iv": t.modelGreeks.impliedVol if t.modelGreeks else None,
            "delta": t.modelGreeks.delta if t.modelGreeks else None,
            "gamma": t.modelGreeks.gamma if t.modelGreeks else None,
        })

    return pd.DataFrame(rows)

def get_technical_signals(ib: IB, tickers: List[str]) -> pd.DataFrame:
    """
    Pulls live technical indicators via IBKR / TWS Gateway.
    """
    HIST_DAYS = 300  # enough for SMA200 / ADX
    SPAN_PCT = 0.05  # ±5% strike window
    N_ATM_STRIKES = 4  # number of strikes on each side of ATM to keep (reduced for speed)
    ATM_DELTA_BAND = 0.10  # |Δ| <= 0.10
    RISK_FREE_RATE = 0.01
    DATA_DIR = "iv_history"
    os.makedirs(DATA_DIR, exist_ok=True)

    # Map yfinance-style futures tickers to (root symbol, exchange)
    FUTURE_ROOTS = {
        "GC=F": ("GC", "COMEX"), "SI=F": ("SI", "COMEX"),
        "CL=F": ("CL", "NYMEX"), "HG=F": ("HG", "COMEX"),
        "NG=F": ("NG", "NYMEX"),
    }

    SYMBOL_MAP = {
        "VIX": (Index, dict(symbol="VIX", exchange="CBOE")),
        "VVIX": (Index, dict(symbol="VVIX", exchange="CBOE")),
        "^TNX": (Index, dict(symbol="TNX", exchange="CBOE")),
        "^TYX": (Index, dict(symbol="TYX", exchange="CBOE")),
    }

    rows = []
    ts_now = datetime.now().isoformat(timespec="seconds")

    # pull SPY once for beta
    spy_ret = pd.Series(dtype=float)
    try:
        spy_bars = ib.reqHistoricalData(
            Stock("SPY", "SMART", "USD"), "", f"{HIST_DAYS} D", "1 day", "TRADES", useRTH=True
        )
        if spy_bars:
            _df = util.df(spy_bars)
            if not _df.empty:
                _df.set_index("date", inplace=True)
                _df.index = pd.to_datetime(_df.index).tz_localize(None)
                spy_ret = _df["close"].pct_change().dropna()
    except Exception as e:
        log.warning("IB hist error SPY: %s", e)

    if spy_ret.empty:
        try:
            spy_df = yf.download("SPY", period=f"{HIST_DAYS}d", interval="1d", progress=False)
            if not spy_df.empty:
                spy_df.rename(columns=str.lower, inplace=True)
                spy_ret = spy_df["close"].pct_change().dropna()
        except Exception as e:
            log.warning("yfinance SPY error: %s", e)

    for tk in tickers:
        log.info("▶ %s", tk)
        if tk == "MOVE":
            log.info("Skipping option chain for MOVE index (no options).")
            continue

        stk = None
        if tk in FUTURE_ROOTS:
            root, exch = FUTURE_ROOTS[tk]
            try:
                stk = front_future(ib, root, exch)
            except Exception as e:
                log.warning("Front future lookup failed for %s: %s", tk, e)
                continue
        elif tk in SYMBOL_MAP:
            cls, kw = SYMBOL_MAP[tk]
            stk = cls(**kw)
        else:
            stk = Stock(tk, "SMART", "USD")
        
        if stk:
            ib.qualifyContracts(stk)
            if not stk.conId:
                log.warning("Could not qualify %s – skipping", tk)
                continue

            bar_type = "TRADES"
            if isinstance(stk, Index):
                bar_type = "MIDPOINT"
            if tk in {"VIX", "VVIX", "^TNX", "^TYX"}:
                bar_type = "TRADES"

            try:
                bars = ib.reqHistoricalData(
                    stk, "", f"{HIST_DAYS} D", "1 day", bar_type, useRTH=True
                )
                df = util.df(bars) if bars else pd.DataFrame()
            except Exception as e:
                log.warning("IB hist error %s: %s", tk, e)
                df = pd.DataFrame()
        else:
            df = pd.DataFrame() # No contract, so no IB data

        if df.empty:
            try:
                yf_df = yf.download(tk, period=f"{HIST_DAYS}d", interval="1d", progress=False)
                yf_df.rename(columns=str.lower, inplace=True)
                yf_df.reset_index(inplace=True)
                yf_df.rename(columns={"date": "date"}, inplace=True)
                df = yf_df
                log.info("Used yfinance bars for %s", tk)
            except Exception as e:
                log.warning("yfinance hist error %s: %s", tk, e)
                continue

        df.set_index("date", inplace=True)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        c, h, l = df["close"], df["high"], df["low"]
        c_ff = c.ffill()

        sma20 = float(c_ff.rolling(20, min_periods=1).mean().iloc[-1])
        sma50 = float(c_ff.rolling(50, min_periods=1).mean().iloc[-1])
        sma200 = float(c_ff.rolling(200, min_periods=1).mean().iloc[-1])
        delta_c = c_ff.diff()
        gain = delta_c.clip(lower=0).rolling(14, min_periods=1).mean()
        loss = (-delta_c.clip(upper=0)).rolling(14, min_periods=1).mean()
        rsi14 = 100 - 100 / (1 + gain / (loss + 1e-9))
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean().iloc[-1]
        plus_dm = (h.diff()).where((h.diff() > l.diff().abs()) & (h.diff() > 0), 0)
        minus_dm = (l.diff()).where((l.diff() > h.diff().abs()) & (l.diff() > 0), 0)
        tr14 = tr.rolling(14).sum()
        pdi = 100 * plus_dm.rolling(14).sum() / tr14
        mdi = 100 * minus_dm.rolling(14).sum() / tr14
        adx14 = ((pdi - mdi).abs() / (pdi + mdi) * 100).rolling(14).mean().iloc[-1]
        ADV30 = df["volume"].tail(30).mean()

        iv_now = np.nan
        oi_near = np.nan
        earn_dt = np.nan

        if stk and stk.secType == "STK":
            try:
                chains = ib.reqSecDefOptParams(tk, "", "STK", stk.conId)
                if not chains:
                    raise Exception("No option-chain data")

                expirations = sorted(chains[0].expirations)
                if not expirations:
                    raise Exception("No expirations")

                trading_classes = getattr(chains[0], "tradingClasses", [])
                root_tc = trading_classes[0] if trading_classes else tk
                expiry = _first_valid_expiry(ib, tk, expirations, c_ff.iloc[-1], root_tc)
                log.info("Selected validated expiry %s for %s", expiry, tk)

                strikes_full = sorted(chains[0].strikes)
                spot = c_ff.iloc[-1]

                if len(strikes_full) >= 2:
                    diffs = np.diff(strikes_full)
                    tick = min(d for d in diffs if d > 0)
                else:
                    tick = 0.5

                atm = round(spot / tick) * tick
                candidate_strikes = [
                    round(atm + i * tick, 2)
                    for i in range(-N_ATM_STRIKES, N_ATM_STRIKES + 1)
                ]
                strikes = [s for s in candidate_strikes if s in strikes_full]

                if not strikes:
                    raise Exception("No candidate strikes found in chain")

                contracts = []
                for s in strikes:
                    s_float = float(s)
                    for r in ("C", "P"):
                        opt = Option(tk, expiry, s_float, r, exchange="SMART", currency="USD")
                        try:
                            det = ib.reqContractDetails(opt)
                            if det and det[0].contract.conId:
                                contracts.append(det[0].contract)
                        except Exception:
                            continue

                if not contracts:
                    raise Exception("No valid option contracts at selected expiry")

                qual = contracts

                for con in qual:
                    try:
                        ib.reqMktData(con, "101,106", False, False)
                    except Exception:
                        continue
                ib.sleep(1.0)
                for con in qual:
                    ib.cancelMktData(con)
                ib.sleep(0.1)

                min_diff = 1e9
                T = (max((datetime.strptime(expiry, "%Y%m%d") - datetime.utcnow()).days, 1) / 365)
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
                    delta_bs = _bs_delta(spot, con.strike, T, RISK_FREE_RATE, iv_, con.right == "C")
                    if abs(delta_bs) <= ATM_DELTA_BAND:
                        oi_sum += oi_
                oi_near = oi_sum

            except Exception as e:
                log.warning("Chain/OI/IV fail for %s: %s", tk, e)

        if (np.isnan(oi_near) or oi_near == 0 or np.isnan(iv_now)) and stk is not None:
            try:
                yft = yf.Ticker(tk)
                if yft.options:
                    yf_expiry = min(
                        yft.options,
                        key=lambda d: abs((pd.to_datetime(d) - pd.to_datetime("today")).days),
                    )
                    oc = yft.option_chain(yf_expiry)

                    spot = c_ff.iloc[-1]

                    def _near(df_yf):
                        return df_yf.loc[(df_yf["strike"] - spot).abs() / spot <= SPAN_PCT]

                    calls, puts = _near(oc.calls), _near(oc.puts)

                    if (np.isnan(oi_near) or oi_near == 0) and (not calls.empty or not puts.empty):
                        oi_near = (
                            calls["openInterest"].fillna(0).sum()
                            + puts["openInterest"].fillna(0).sum()
                        )

                    if np.isnan(iv_now) and not calls.empty:
                        iv_now = calls.loc[
                            (calls["strike"] - spot).abs().idxmin(), "impliedVolatility"
                        ]
            except Exception as e:
                log.debug("yfinance option fallback error for %s: %s", tk, e)

        fn = os.path.join(DATA_DIR, f"{tk}.csv")
        if not np.isnan(iv_now):
            today = datetime.utcnow().strftime("%Y-%m-%d")
            pd.DataFrame([[today, iv_now]], columns=["date", "iv"]).to_csv(
                fn, mode="a", header=not os.path.exists(fn), index=False
            )
        iv_hist = (
            pd.read_csv(fn).drop_duplicates("date").tail(252)["iv"]
            if os.path.exists(fn)
            else pd.Series()
        )
        iv_rank = (
            np.nan
            if iv_hist.empty or iv_hist.max() == iv_hist.min()
            else (iv_now - iv_hist.min()) / (iv_hist.max() - iv_hist.min()) * 100
        )

        beta = np.nan
        if not spy_ret.empty:
            ret = c_ff.pct_change().dropna()
            common = spy_ret.index.intersection(ret.index)
            if len(common) > 10:
                beta = (
                    np.cov(ret.loc[common], spy_ret.loc[common])[0, 1]
                    / spy_ret.loc[common].var()
                )

        if earn_dt is np.nan or pd.isna(earn_dt):
            try:
                ed_df = yf.Ticker(tk).get_earnings_dates(limit=1)
                if not ed_df.empty:
                    earn_dt = (
                        pd.to_datetime(ed_df["Earnings Date"].iloc[0]).date().isoformat()
                    )
            except Exception:
                try:
                    cal = yf.Ticker(tk).calendar
                    if not cal.empty and "Earnings Date" in cal.index:
                        edm = cal.loc["Earnings Date"][0]
                        if not pd.isna(edm):
                            earn_dt = pd.to_datetime(edm).date().isoformat()
                except Exception:
                    pass

        rows.append(
            dict(
                timestamp=ts_now,
                ticker=tk,
                ADX=adx14,
                ATR=atr14,
                _20dma=sma20,
                _50dma=sma50,
                _200dma=sma200,
                IV_rank=iv_rank,
                RSI=rsi14,
                beta_SPY=beta,
                ADV30=ADV30,
                next_earnings=earn_dt,
                OI_near_ATM=oi_near,
            )
        )
        ib.sleep(0.05)

    return pd.DataFrame(rows)
''
