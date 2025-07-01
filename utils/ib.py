
"""
ib.py - Centralized IBKR connection and data fetching.
"""
import logging
from typing import List, Optional, Set, Tuple, Dict, Any
from datetime import datetime
import os
import time

import pandas as pd
import yfinance as yf
from ib_insync import IB, Contract, Option, Stock, Index, Future, Ticker, Position, util

try:
    from pandas_datareader import data as web
    FRED_AVAILABLE = True
except ImportError:
    FRED_AVAILABLE = False

# --- Configuration ---
IB_HOST = "127.0.0.1"
IB_PORT = 7497
# Use a dedicated client ID for this utility module
CLIENT_ID = 20

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# Silence noisy ib_insync logs
for logger_name in ("ib_insync.client", "ib_insync.wrapper", "ib_insync.ib"):
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)


class IBManager:
    """A context manager for handling IBKR connections."""

    def __init__(self, host: str = IB_HOST, port: int = IB_PORT, client_id: int = CLIENT_ID):
        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id

    def __enter__(self) -> IB:
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=10)
            # Switch to delayed data if live is not available
            if not self.ib.reqMarketDataType(1): # 1 for live
                self.ib.reqMarketDataType(3) # 3 for delayed
            log.info(f"Connected to IBKR at {self.host}:{self.port}")
        except Exception as e:
            log.error(f"Failed to connect to IBKR: {e}")
            raise ConnectionError("Could not connect to IBKR Gateway/TWS.") from e
        return self.ib

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.ib.isConnected():
            self.ib.disconnect()
            log.info("Disconnected from IBKR.")


def get_positions(ib: IB) -> pd.DataFrame:
    """
    Fetches current portfolio positions from Interactive Brokers.
    """
    positions = ib.positions()
    if not positions:
        return pd.DataFrame()

    contracts = [p.contract for p in positions]
    tickers = ib.reqTickers(*contracts)

    price_map = {t.contract.conId: t.marketPrice() for t in tickers}

    rows = []
    for p in positions:
        mark_price = price_map.get(p.contract.conId, p.avgCost)
        rows.append({
            "symbol": p.contract.symbol,
            "secType": p.contract.secType,
            "position": p.position,
            "avg_cost": p.avgCost,
            "mark_price": mark_price,
            "market_value": p.position * mark_price * float(p.contract.multiplier or 1),
            "unrealized_pnl": (mark_price - p.avgCost) * p.position * float(p.contract.multiplier or 1),
        })

    return pd.DataFrame(rows)


def load_ib_positions_ib(
    ib: IB,
) -> pd.DataFrame:
    """
    Pull current portfolio positions directly from Interactive Brokers via
    the TWS / IB-Gateway API (ib_insync wrapper).

    Columns returned: symbol · quantity · cost basis · mark price ·
    market_value · unrealized_pnl
    """
    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id)
        # suppress per-contract error spam from IB
        ib.errorEvent += lambda *a, **k: None
    except Exception as e:
        raise ConnectionError(
            f"❌ Cannot connect to IB API at {host}:{port}  →  {e}"
        ) from e

    positions = ib.positions()
    if not positions:
        ib.disconnect()
        raise RuntimeError(
            "API returned no positions. Confirm account is logged in and the "
            "API user has permissions."
        )

    contracts = [p.contract for p in positions]
    # Request real-time market data in a single call
    tickers = ib.reqTickers(*contracts)

    # Build a quick {conId: last_price} map
    price_map = {}
    for t in tickers:
        # fall back to mid-point if last==0
        last = t.last if t.last else (t.bid + t.ask) / 2 if (t.bid and t.ask) else None
        price_map[t.contract.conId] = last

    rows = []
    for p in positions:
        symbol = p.contract.symbol
        qty = p.position
        cost_basis = p.avgCost
        mark_price = price_map.get(p.contract.conId)
        # --- Fallback: try yfinance close if IB API did not return a price
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

    return df


def _tickers_from_ib(ib: IB) -> list[str]:
    """Return unique stock tickers from current IBKR account positions."""
    positions = ib.positions()
    if not positions:
        return []
    # extract underlying symbol for stocks only
    tickers = {
        p.contract.symbol.upper() for p in positions if p.contract.secType == "STK"
    }
    return sorted(tickers)


PORTFOLIO_FILES = ["tickers_live.txt", "tickers.txt"]
EXTRA_TICKERS = ["SPY", "QQQ", "IWM", "^VIX", "DX-Y.NYB"]
PROXY_MAP = {"VIX": "^VIX", "VVIX": "^VVIX", "DXY": "DX-Y.NYB"}
YIELD_MAP = {"US2Y": "DGS2", "US10Y": "DGS10", "US20Y": "DGS20", "US30Y": "DGS30"}


def load_tickers(ib: IB) -> list[str]:
    """Return unique tickers prioritising IBKR holdings; otherwise text file."""
    # 1) try IBKR
    ib_tickers = _tickers_from_ib(ib)
    if ib_tickers:
        mapped_ib = [PROXY_MAP.get(t, t) for t in ib_tickers]
        return sorted(set(mapped_ib + EXTRA_TICKERS))

    # 2) fallback to file
    path = next((p for p in PORTFOLIO_FILES if os.path.exists(p)), None)
    user_tickers = []
    if path:
        with open(path) as f:
            user_tickers = [line.strip().upper() for line in f if line.strip()]
    mapped = [PROXY_MAP.get(t, t) for t in user_tickers]
    return sorted(set(mapped + EXTRA_TICKERS))

def get_option_positions(ib: IB) -> Tuple[List[Option], Set[str]]:
    """Return option contracts in the IBKR account and their underlying symbols."""
    opt_cons: List[Option] = []
    underlyings: Set[str] = set()
    for pos in ib.positions():
        c = pos.contract
        if getattr(c, "secType", "") == "OPT":
            opt_cons.append(c)
            underlyings.add(c.symbol)
    return opt_cons, underlyings


def fetch_ib_quotes(ib: IB, tickers: List[str], opt_cons: List[Option]) -> pd.DataFrame:
    """Return DataFrame of quotes for symbols IB can serve; missing ones flagged NaN."""
    combined_rows: List[Dict] = []
    reqs: Dict[str, Any] = {}

    for tk in tickers:
        if tk.endswith("=F") or tk in YIELD_MAP:
            continue
        if tk in SYMBOL_MAP:
            cls, kw = SYMBOL_MAP[tk]
            con = cls(**kw)
        else:
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
                "last": (
                    md.last / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.last
                    else md.last
                ),
                "bid": (
                    md.bid / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.bid
                    else md.bid
                ),
                "ask": (
                    md.ask / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.ask
                    else md.ask
                ),
                "open": (
                    md.open / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.open
                    else md.open
                ),
                "high": (
                    md.high / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.high
                    else md.high
                ),
                "low": (
                    md.low / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.low
                    else md.low
                ),
                "prev_close": (
                    md.close / 10
                    if key in {"^IRX", "^FVX", "^TNX", "^TYX"} and md.close
                    else md.close
                ),
                "volume": md.volume,
                "source": "IB",
            }
        )
        ib.cancelMktData(md.contract)

    return pd.DataFrame(combined_rows)


def fetch_yf_quotes(tickers: List[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        if t in YIELD_MAP:
            continue
        yf_tkr = PROXY_MAP.get(t, t)
        try:
            info = yf.Ticker(yf_tkr).info
            price = info.get("regularMarketPrice")
            bid = info.get("bid")
            ask = info.get("ask")
            day_high = info.get("dayHigh")
            day_low = info.get("dayLow")
            prev_close = info.get("previousClose")
            vol = info.get("volume")
        except Exception as e:
            try:
                hist = yf.download(yf_tkr, period="2d", interval="1d", progress=False)
                price = hist["Close"].iloc[-1] if not hist.empty else np.nan
                prev_close = hist["Close"].iloc[-2] if len(hist) > 1 else np.nan
                bid = ask = day_high = day_low = vol = np.nan
                log.warning("yfinance info fail %s, used download(): %s", t, e)
            except Exception as e2:
                log.warning("yfinance miss %s: %s", t, e2)
                continue
        if t in {"^IRX", "^FVX", "^TNX", "^TYX"} and price is not None:
            price = price / 10.0
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
    df = pd.DataFrame(rows)
    return df


def fetch_fred_yields(tickers: List[str]) -> pd.DataFrame:
    if not FRED_AVAILABLE:
        return pd.DataFrame()
    rows = []
    for t in tickers:
        series = YIELD_MAP.get(t)
        if not series:
            continue
        try:
            val = web.DataReader(series, "fred").iloc[-1].values[0]
            rows.append(
                {
                    "ticker": t,
                    "last": val,
                    "bid": np.nan,
                    "ask": np.nan,
                    "open": np.nan,
                    "high": np.nan,
                    "low": np.nan,
                    "prev_close": np.nan,
                    "volume": np.nan,
                    "source": "FRED",
                }
            )
        except Exception as e:
            log.warning("FRED miss %s: %s", t, e)
    return pd.DataFrame(rows)


def fetch_live_positions(ib: IB) -> pd.DataFrame:
    """
    Return a DataFrame with real-time P&L for ALL open positions in the account.
    """
    try:
        positions = ib.positions()
    except Exception as e:
        log.warning("IB positions() failed: %s", e)
        return pd.DataFrame()

    rows: List[Dict] = []
    ts_now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")

    combo_counts: Dict[Tuple[str, str], int] = {}
    for pos in positions:
        c = pos.contract
        if c.secType == "OPT":
            key = (c.symbol, getattr(c, "lastTradeDateOrContractMonth", ""))
            combo_counts[key] = combo_counts.get(key, 0) + 1

    combo_leg_con_ids = set()
    for pos in positions:
        if pos.contract.secType == "BAG" and pos.contract.comboLegs:
            for leg in pos.contract.comboLegs:
                combo_leg_con_ids.add(leg.conId)

    md_reqs = {}
    for pos in positions:
        con = pos.contract
        if con.conId in combo_leg_con_ids:
            continue

        try:
            (ql,) = ib.qualifyContracts(con)
            md = ib.reqMktData(ql, "", False, False)
            md_reqs[con.conId] = (con, md, pos.avgCost, pos.position)
        except Exception:
            continue

    ib.sleep(4.0)

    for conId, (con, md, avg_cost, qty) in md_reqs.items():
        raw_last = md.last if md.last is not None else md.close
        last = raw_last
        mult = int(con.multiplier) if con.multiplier else 1
        cost_basis = avg_cost * qty * mult
        market_val = last * qty * mult
        unreal_pnl = (last - avg_cost) * qty * mult
        unreal_pct = (unreal_pnl / cost_basis * 100) if cost_basis else np.nan

        combo_legs_data = []
        if con.secType == "BAG" and con.comboLegs:
            for leg in con.comboLegs:
                leg_contract = ib.qualifyContracts(Contract(conId=leg.conId, exchange=leg.exchange))[0]
                combo_legs_data.append({
                    "symbol": leg_contract.symbol,
                    "sec_type": leg_contract.secType,
                    "expiry": getattr(leg_contract, "lastTradeDateOrContractMonth", None),
                    "strike": getattr(leg_contract, "strike", None),
                    "right": getattr(leg_contract, "right", None),
                    "ratio": leg.ratio,
                    "action": leg.action,
                    "exchange": leg.exchange,
                })

        rows.append(
            {
                "timestamp": ts_now,
                "ticker": con.symbol,
                "secType": (
                    "OPT_COMBO"
                    if (
                        con.secType == "BAG"
                        or (
                            con.secType == "OPT"
                            and combo_counts.get(
                                (con.symbol, getattr(con, "lastTradeDateOrContractMonth", ""))
                            , 0) > 1
                        )
                    )
                    else con.secType
                ),
                "position": qty,
                "avg_cost": avg_cost,
                "last": last,
                "market_value": market_val,
                "cost_basis": cost_basis,
                "unrealized_pnl_pct": unreal_pct,
                "unrealized_pnl": unreal_pnl,
                "combo_legs": combo_legs_data if combo_legs_data else None,
            }
        )
        ib.cancelMktData(md.contract)

    return pd.DataFrame(rows)


SYMBOL_MAP = {
    "VIX": (Index, dict(symbol="VIX", exchange="CBOE")),
    "VVIX": (Index, dict(symbol="VVIX", exchange="CBOE")),
    "^TNX": (Index, dict(symbol="TNX", exchange="CBOE")),
    "^TYX": (Index, dict(symbol="TYX", exchange="CBOE")),
    "^IRX": (Index, dict(symbol="IRX", exchange="CBOE")),
    "^FVX": (Index, dict(symbol="FVX", exchange="CBOE")),
}

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
    return datetime(1900, 1, 1)


def _first_valid_expiry(
    ib: IB, symbol: str, expirations: list[str], spot: float, root_tc: str
) -> str:
    """
    Return the first expiry whose chain has a *valid* ATM contract.
    Falls back to earliest expiry if none validate.
    """
    for exp in sorted(expirations, key=lambda d: pd.to_datetime(d)):
        atm = round(spot)  # simple ATM guess, refined later
        try:
            test = Option(
                symbol,
                exp,
                atm,
                "C",
                exchange="SMART",
                currency="USD",
                tradingClass=root_tc,
            )
            det = ib.reqContractDetails(test)
            if det and det[0].contract.conId:
                return exp
        except Exception:
            continue
    return expirations[0]


def front_future(ib: IB, root: str, exch: str) -> Future:
    """
    Return the nearest non-expired future contract for root/exchange.
    """
    details = ib.reqContractDetails(Future(root, exchange=exch))
    if not details:
        raise ValueError("no contract details")
    for det in sorted(
        details, key=lambda d: _parse_ib_month(d.contract.lastTradeDateOrContractMonth)
    ):
        dt = _parse_ib_month(det.contract.lastTradeDateOrContractMonth)
        if dt > datetime.utcnow():
            return det.contract
    return details[0].contract
''

