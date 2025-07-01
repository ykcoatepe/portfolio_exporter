from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List
import os

import pandas as pd
import numpy as np
import yfinance as yf

try:
    from ib_insync import IB, Option, Stock

    IB_AVAILABLE = True
except Exception:  # pragma: no cover - optional
    IB_AVAILABLE = False
    IB = Option = Stock = None  # type: ignore

from utils.progress import iter_progress

EXTRA_TICKERS = ["SPY", "QQQ", "IWM", "^VIX", "DX-Y.NYB"]
PROXY_MAP = {"VIX": "^VIX", "VVIX": "^VVIX", "DXY": "DX-Y.NYB"}
PORTFOLIO_FILES = ["tickers_live.txt", "tickers.txt"]


def _tickers_from_ib() -> list[str]:
    if not IB_AVAILABLE:
        return []
    ib = IB()
    try:
        ib.connect("127.0.0.1", 7497, clientId=3, timeout=3)
    except Exception:
        return []
    positions = ib.positions()
    ib.disconnect()
    if not positions:
        return []
    tickers = {
        p.contract.symbol.upper() for p in positions if p.contract.secType == "STK"
    }
    return sorted(tickers)


def load_tickers() -> list[str]:
    ib_tickers = _tickers_from_ib()
    if ib_tickers:
        mapped_ib = [PROXY_MAP.get(t, t) for t in ib_tickers]
        return sorted(set(mapped_ib + EXTRA_TICKERS))

    path = next((p for p in PORTFOLIO_FILES if os.path.exists(p)), None)
    user_tickers: list[str] = []
    if path:
        with open(path) as f:
            user_tickers = [line.strip().upper() for line in f if line.strip()]
    mapped = [PROXY_MAP.get(t, t) for t in user_tickers]
    return sorted(set(mapped + EXTRA_TICKERS))


def fetch_and_prepare_data(tickers: List[str]) -> pd.DataFrame:
    if not tickers:
        raise ValueError("No data fetched for any ticker.")
    data = yf.download(
        tickers=tickers,
        period="60d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
    )
    columns = ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]
    if data.empty:
        return pd.DataFrame(columns=columns)
    dfs = []
    if isinstance(data.columns, pd.MultiIndex):
        iterable = iter_progress(tickers, "split") if tickers else tickers
        for ticker in iterable:
            if ticker in data:
                df_t = data[ticker].reset_index()
                df_t["Ticker"] = ticker
                dfs.append(df_t)
    else:
        df_t = data.reset_index()
        df_t["Ticker"] = tickers[0]
        dfs.append(df_t)
    result = pd.concat(dfs, ignore_index=True)
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


# ---------------------------------------------------------------------------
# IB portfolio positions
# ---------------------------------------------------------------------------


def load_ib_positions_ib(
    host: str = "127.0.0.1", port: int = 7497, client_id: int = 999
) -> pd.DataFrame:
    """Return current IBKR portfolio positions with market prices."""
    if IB is None:
        return pd.DataFrame()

    ib = IB()
    ib.connect(host, port, clientId=client_id)
    ib.errorEvent += lambda *a, **k: None

    positions = ib.positions()
    contracts = [p.contract for p in positions]
    tickers = ib.reqTickers(*contracts)
    price_map = {}
    for t in tickers:
        last = t.last if t.last else (t.bid + t.ask) / 2 if (t.bid and t.ask) else None
        price_map[t.contract.conId] = last

    rows = []
    for p in positions:
        symbol = p.contract.symbol
        qty = p.position
        cost_basis = p.avgCost
        mark_price = price_map.get(p.contract.conId)
        if mark_price is None or pd.isna(mark_price):
            try:
                yq = yf.Ticker(symbol).history(period="1d")["Close"]
                mark_price = float(yq.iloc[-1]) if not yq.empty else None
            except Exception:
                mark_price = None
        side = "Short" if qty < 0 else "Long"
        rows.append(
            {
                "symbol": symbol,
                "side": side,
                "quantity": abs(qty),
                "cost basis": cost_basis,
                "mark price": mark_price,
            }
        )

    df = pd.DataFrame(rows)
    df["market_value"] = df["quantity"] * df["mark price"]
    df["unrealized_pnl"] = (df["mark price"] - df["cost basis"]) * df["quantity"]
    ib.disconnect()
    return df


# ---------------------------------------------------------------------------
# Historical OHLC
# ---------------------------------------------------------------------------


def fetch_ohlc(tickers: List[str], days_back: int = 60) -> pd.DataFrame:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)
    data = yf.download(
        tickers,
        start=start.date(),
        end=end.date() + timedelta(days=1),
        group_by="ticker",
        auto_adjust=False,
        progress=False,
    )
    rows = []
    for t in iter_progress(tickers, "Processing tickers"):
        d = data[t].dropna().reset_index()
        d.columns = ["date", "open", "high", "low", "close", "adj_close", "volume"]
        d["ticker"] = t
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


# ---------------------------------------------------------------------------
# Live quotes (IB & Yahoo)
# ---------------------------------------------------------------------------


def fetch_ib_quotes(tickers: List[str], opt_cons: List[Option]) -> pd.DataFrame:
    if IB is None:
        return pd.DataFrame()

    ib = IB()
    try:
        ib.connect("127.0.0.1", 7497, clientId=2, timeout=3)
    except Exception:
        logging.warning("IBKR Gateway not reachable — skipping IB pull.")
        return pd.DataFrame()

    combined_rows: list[dict] = []
    reqs: dict[str, any] = {}
    for tk in tickers:
        con = Stock(tk, "SMART", "USD")
        try:
            ql = ib.qualifyContracts(con)
            if not ql:
                raise ValueError("not qualified")
            md = ib.reqMktData(ql[0], "", False, False)
            reqs[tk] = md
        except Exception:
            continue

    for opt in opt_cons:
        try:
            ql = ib.qualifyContracts(opt)
            if not ql:
                continue
            md = ib.reqMktData(ql[0], "", False, False)
            reqs[opt.localSymbol] = md
        except Exception:
            continue

    ib.sleep(4.0)

    for key, md in reqs.items():
        combined_rows.append(
            {
                "ticker": key,
                "last": md.last,
                "bid": md.bid,
                "ask": md.ask,
                "open": md.open,
                "high": md.high,
                "low": md.low,
                "prev_close": md.close,
                "volume": md.volume,
                "source": "IB",
            }
        )
        ib.cancelMktData(md.contract)

    ib.disconnect()
    return pd.DataFrame(combined_rows)


def fetch_yf_quotes(tickers: List[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            price = info.get("regularMarketPrice")
            bid = info.get("bid")
            ask = info.get("ask")
            day_high = info.get("dayHigh")
            day_low = info.get("dayLow")
            prev_close = info.get("previousClose")
            vol = info.get("volume")
        except Exception:
            try:
                hist = yf.download(t, period="2d", interval="1d", progress=False)
                price = hist["Close"].iloc[-1] if not hist.empty else np.nan
                prev_close = hist["Close"].iloc[-2] if len(hist) > 1 else np.nan
                bid = ask = day_high = day_low = vol = np.nan
            except Exception:
                continue
        rows.append(
            {
                "ticker": t,
                "last": price,
                "bid": bid,
                "ask": ask,
                "open": info.get("open") if "info" in locals() else np.nan,
                "high": day_high,
                "low": day_low,
                "prev_close": prev_close,
                "volume": vol,
                "source": "YF",
            }
        )
        time.sleep(0.1)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Option chain snapshot (wrapper)
# ---------------------------------------------------------------------------


def snapshot_chain(ib: IB, symbol: str, expiry_hint: str | None = None) -> pd.DataFrame:
    from option_chain_snapshot import snapshot_chain as _snap

    return _snap(ib, symbol, expiry_hint)
