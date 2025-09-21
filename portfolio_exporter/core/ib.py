from __future__ import annotations

import asyncio
import math
import threading
from typing import Any

from portfolio_exporter.core.config import settings
from portfolio_exporter.core.ib_config import HOST as _IB_HOST
from portfolio_exporter.core.ib_config import PORT as _IB_PORT
from portfolio_exporter.core.ib_config import client_id as _client_id

_IB_CID = _client_id("core", default=29)

_ib_singleton = None  # type: ignore


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """Return a running event loop, creating one in this thread if needed."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        threading.current_thread()._loop = loop  # keep ref for GC
        asyncio.set_event_loop(loop)
        return loop


def _ib():
    """Return a cached IB connection if available."""
    global _ib_singleton
    try:
        from ib_insync import IB  # type: ignore
    except Exception:
        IB = None  # type: ignore
    if _ib_singleton and hasattr(_ib_singleton, "isConnected") and _ib_singleton.isConnected():
        return _ib_singleton
    if IB is None:
        return None
    _ib_singleton = IB()

    async def _try_connect():
        try:
            await _ib_singleton.connectAsync(_IB_HOST, _IB_PORT, clientId=_IB_CID, timeout=2)
        except Exception:
            pass

    loop = _ensure_loop()
    if loop.is_running():
        asyncio.run_coroutine_threadsafe(_try_connect(), loop)
    else:
        loop.run_until_complete(_try_connect())
    return _ib_singleton


def quote_stock(symbol: str) -> dict[str, Any]:
    """Fetch snapshot quote for a stock.

    Attempts IBKR first and falls back to yfinance.
    """
    ib = _ib()
    if ib is not None and hasattr(ib, "isConnected") and ib.isConnected():
        try:
            from ib_insync import Stock  # type: ignore
        except Exception:
            Stock = None  # type: ignore
        stk = Stock(symbol, "SMART", "USD") if Stock else None
        ticker = ib.reqMktData(stk, "", snapshot=True) if stk else None
        ib.sleep(0.3)
        mid = (
            (ticker.bid + ticker.ask) / 2
            if ticker and ticker.bid and ticker.ask
            else (ticker.last if ticker else None)
        )
        # IB can return blanks outside RTH; if so, fall back to yfinance
        if mid is None or (isinstance(mid, float) and math.isnan(mid)):
            try:
                ib.disconnect()
            except Exception:
                pass
        else:
            return {"mid": mid, "bid": ticker.bid, "ask": ticker.ask}
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        yf = None  # type: ignore
    yf_tkr = yf.Ticker(symbol) if yf else None
    price = yf_tkr.history(period="1d")["Close"].iloc[-1] if yf_tkr is not None else float("nan")
    return {"mid": price, "bid": price, "ask": price}


def quote_option(symbol: str, expiry: str, strike: float, right: str) -> dict[str, Any]:
    """Return price and greeks for an option contract.

    Args:
        symbol: Underlying symbol (e.g. ``"SPY"``).
        expiry: Expiration in ``YYYY-MM-DD`` format.
        strike: Strike price.
        right: ``"C"`` for calls or ``"P"`` for puts.

    Returns:
        Dictionary with keys ``mid``, ``bid``, ``ask``, ``delta``, ``gamma``,
        ``vega``, ``theta`` and ``iv``.
    """
    ib = _ib()
    if ib is not None and hasattr(ib, "isConnected") and ib.isConnected():
        try:
            from ib_insync import Option  # type: ignore
        except Exception:
            Option = None  # type: ignore
        # IB expects yyyymmdd string for lastTradeDateOrContractMonth
        opt = Option(symbol, expiry.replace("-", ""), strike, right, "SMART", "USD") if Option else None
        ticker = ib.reqMktData(opt, "", snapshot=True) if opt else None
        ib.sleep(0.3)
        mid = (
            (ticker.bid + ticker.ask) / 2
            if ticker and ticker.bid and ticker.ask
            else (ticker.last if ticker else None)
        )
        if mid is None or (isinstance(mid, float) and math.isnan(mid)):
            # empty snapshot → disconnect so we hit the fallback below
            try:
                ib.disconnect()
            except Exception:
                pass
        else:
            g = ticker.modelGreeks
            return {
                "mid": mid,
                "bid": ticker.bid,
                "ask": ticker.ask,
                "delta": getattr(g, "delta", math.nan),
                "gamma": getattr(g, "gamma", math.nan),
                "vega": getattr(g, "vega", math.nan),
                "theta": getattr(g, "theta", math.nan),
                "iv": getattr(g, "impliedVol", math.nan),
            }
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        yf = None  # type: ignore
    yf_tkr = yf.Ticker(symbol) if yf else None
    chain = yf_tkr.option_chain(expiry) if yf_tkr is not None else None
    tbl = chain.calls if (chain is not None and right == "C") else (chain.puts if chain is not None else None)
    row = tbl.loc[tbl["strike"] == strike] if tbl is not None else None
    if row.empty:
        raise ValueError("Strike not found in yfinance chain")
    bid = row["bid"].values[0]
    ask = row["ask"].values[0]
    iv = row["impliedVolatility"].values[0]
    mid = (bid + ask) / 2
    q = {
        "mid": mid,
        "bid": bid,
        "ask": ask,
        "delta": math.nan,
        "gamma": math.nan,
        "vega": math.nan,
        "theta": math.nan,
        "iv": iv,
    }
    if (
        (q["delta"] is None or (isinstance(q["delta"], float) and math.isnan(q["delta"])))
        and iv
        and not math.isnan(iv)
    ):
        from datetime import date

        from portfolio_exporter.core.greeks import bs_greeks

        hist = yf_tkr.history(period="1d") if yf_tkr is not None else None
        spot = hist["Close"].iloc[-1] if (hist is not None and not hist.empty) else strike
        expiry_dt = date.fromisoformat(expiry)
        t = (expiry_dt - date.today()).days / 365
        mult = 100
        greeks = bs_greeks(
            spot,
            strike,
            t,
            settings.greeks.risk_free,
            iv,
            call=(right == "C"),
            multiplier=mult,
        )
        q.update(greeks)
    return q


def net_liq() -> float:
    """Return current NetLiquidation or NaN if unavailable."""

    ib = _ib()
    if not ib.isConnected():
        return float("nan")
    try:
        for row in ib.accountSummary():
            if getattr(row, "tag", "") == "NetLiquidation":
                return float(row.value)
    except Exception:
        return float("nan")
    return float("nan")
