from __future__ import annotations

import contextlib
import math
from typing import Any, Dict

import yfinance as yf
from ib_insync import IB, Option, Stock

_IB_HOST, _IB_PORT, _IB_CID = "127.0.0.1", 7497, 29

_ib_singleton: IB | None = None


def _ib() -> IB:
    """Return a cached IB connection if available."""
    global _ib_singleton
    if _ib_singleton and _ib_singleton.isConnected():
        return _ib_singleton
    _ib_singleton = IB()
    with contextlib.suppress(Exception):
        _ib_singleton.connect(_IB_HOST, _IB_PORT, clientId=_IB_CID, timeout=2)
    return _ib_singleton


def quote_stock(symbol: str) -> Dict[str, Any]:
    """Fetch snapshot quote for a stock.

    Attempts IBKR first and falls back to yfinance.
    """
    ib = _ib()
    if ib.isConnected():
        stk = Stock(symbol, "SMART", "USD")
        ticker = ib.reqMktData(stk, "", snapshot=True)
        ib.sleep(0.3)
        mid = (
            (ticker.bid + ticker.ask) / 2 if ticker.bid and ticker.ask else ticker.last
        )
        # IB can return blanks outside RTH; if so, fall back to yfinance
        if mid is None or (isinstance(mid, float) and math.isnan(mid)):
            ib.disconnect()
        else:
            return {"mid": mid, "bid": ticker.bid, "ask": ticker.ask}
    yf_tkr = yf.Ticker(symbol)
    price = yf_tkr.history(period="1d")["Close"].iloc[-1]
    return {"mid": price, "bid": price, "ask": price}


def quote_option(symbol: str, expiry: str, strike: float, right: str) -> Dict[str, Any]:
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
    if ib.isConnected():
        # IB expects yyyymmdd string for lastTradeDateOrContractMonth
        opt = Option(symbol, expiry.replace("-", ""), strike, right, "SMART", "USD")
        ticker = ib.reqMktData(opt, "", snapshot=True)
        ib.sleep(0.3)
        mid = (
            (ticker.bid + ticker.ask) / 2 if ticker.bid and ticker.ask else ticker.last
        )
        if mid is None or (isinstance(mid, float) and math.isnan(mid)):
            # empty snapshot → disconnect so we hit the fallback below
            ib.disconnect()
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

    yf_tkr = yf.Ticker(symbol)
    chain = yf_tkr.option_chain(expiry)
    tbl = chain.calls if right == "C" else chain.puts
    row = tbl.loc[tbl["strike"] == strike]
    if row.empty:
        raise ValueError("Strike not found in yfinance chain")
    mid = (row["bid"].values[0] + row["ask"].values[0]) / 2
    return {
        "mid": mid,
        "bid": row["bid"].values[0],
        "ask": row["ask"].values[0],
        "delta": math.nan,
        "gamma": math.nan,
        "vega": math.nan,
        "theta": math.nan,
        "iv": row["impliedVolatility"].values[0],
    }
