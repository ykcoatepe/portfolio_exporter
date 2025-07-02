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
    from ib_insync.contract import Contract
    from ib_insync.ticker import Ticker
    from ib_insync.objects import Position
    IB_AVAILABLE = True
except Exception:  # pragma: no cover - optional
    IB_AVAILABLE = False
    IB = Option = Stock = Contract = Ticker = Position = None  # type: ignore

from utils.progress import iter_progress
from bisect import bisect_left
from zoneinfo import ZoneInfo
from utils.bs import bs_greeks

EXTRA_TICKERS = ["SPY", "QQQ", "IWM", "^VIX", "DX-Y.NYB"]
PROXY_MAP = {"VIX": "^VIX", "VVIX": "^VVIX", "DXY": "DX-Y.NYB"}
PORTFOLIO_FILES = ["tickers_live.txt", "tickers.txt"]
CURRENCIES = ['EUR', 'JPY', 'GBP', 'AUD', 'CAD', 'CHF', 'CNY', 'HKD', 'NZD', 'SEK', 'KRW', 'SGD', 'NOK', 'MXN', 'INR', 'RUB', 'ZAR', 'TRY', 'BRL']

# IBKR Connection Details
IB_HOST = "127.0.0.1"
IB_PORT = 7497
IB_CLIENT_ID = 10 # Default client ID for option chain snapshot, can be overridden if needed


def _tickers_from_ib() -> list[str]:
    if not IB_AVAILABLE:
        return []
    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, IB_CLIENT_ID, timeout=3)
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


def get_portfolio_tickers_from_ib(
    host: str = IB_HOST, port: int = IB_PORT, client_id: int = IB_CLIENT_ID
) -> List[str]:
    """Return unique underlying tickers from all IBKR portfolio positions."""
    if not IB_AVAILABLE:
        return []

    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id, timeout=3)
    except Exception:
        logging.warning("IBKR Gateway not reachable — cannot fetch portfolio tickers.")
        return []

    positions = ib.positions()
    ib.disconnect()

    unique_tickers = set()
    for p in positions:
        symbol = p.contract.symbol.upper()
        unique_tickers.add(PROXY_MAP.get(symbol, symbol))

    return sorted(list(unique_tickers))

def load_ib_positions_ib(
    host: str = IB_HOST, port: int = IB_PORT, client_id: int = IB_CLIENT_ID
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
    """Fetch historical OHLC data for a list of tickers, handling currency pairs."""
    formatted_tickers = []
    for ticker in tickers:
        if ticker.upper() in CURRENCIES:
            formatted_tickers.append(f"{ticker.upper()}USD=X")
        else:
            formatted_tickers.append(ticker)

    if not formatted_tickers:
        return pd.DataFrame()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)
    data = yf.download(
        tickers=formatted_tickers,
        start=start.date(),
        end=end.date() + timedelta(days=1),
        group_by="ticker",
        auto_adjust=False,
        progress=False,
    )

    if data.empty:
        return pd.DataFrame()

    rows = []
    for ticker in iter_progress(formatted_tickers, "Processing tickers"):
        # Check if the original ticker or the formatted ticker is in the data columns
        original_ticker = ticker.replace("USD=X", "")
        if ticker in data:
            df_t = data[ticker].dropna().reset_index()
            df_t.columns = ["date", "open", "high", "low", "close", "adj_close", "volume"]
            df_t["ticker"] = original_ticker  # Use the original ticker for consistency
            rows.append(df_t)
        elif original_ticker in data:
            df_t = data[original_ticker].dropna().reset_index()
            df_t.columns = ["date", "open", "high", "low", "close", "adj_close", "volume"]
            df_t["ticker"] = original_ticker
            rows.append(df_t)

    if not rows:
        return pd.DataFrame()

    return pd.concat(rows, ignore_index=True)


# ---------------------------------------------------------------------------
# Live quotes (IB & Yahoo)
# ---------------------------------------------------------------------------


def fetch_ib_quotes(tickers: List[str], opt_cons: List[Option]) -> pd.DataFrame:
    if IB is None:
        return pd.DataFrame()

    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, IB_CLIENT_ID, timeout=3)
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



# ---------------------------------------------------------------------------
# Option chain snapshot (wrapper)
# ---------------------------------------------------------------------------

# ── helper: get reliable split‑adjusted spot ──
def _safe_spot(ib: IB, stk: Stock, streaming_tk):
    """
    Return a trustworthy spot:
      • live/frozen bid/ask or last if available
      • else previous regular‑session close (split‑adjusted).
    """
    spot_val = streaming_tk.marketPrice() or streaming_tk.last
    if spot_val and spot_val > 0:
        return spot_val
    # pull adjusted close (1‑day bar, regular trading hours)
    bars = ib.reqHistoricalData(
        stk,
        endDateTime="",
        durationStr="1 D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
    )
    return bars[-1].close if bars else np.nan


# ─────────── contract resolution helper ───────────
def _resolve_contract(ib: IB, template: Option):
    """
    Return a fully‑qualified Contract for the given template, handling
    ambiguous matches via `ib.qualifyContracts` first (fast‑path) and
    falling back to `reqContractDetails` only if qualification fails.

    Preference order for ambiguous matches:
      1. tradingClass equal to the underlying symbol
      2. first contract returned by IB

    Returns None if no contract can be qualified.
    """
    # --- fast path: qualifyContracts ----------------------------------------------------
    try:
        ql = ib.qualifyContracts(template)
        if ql:
            # If there is only one qualified contract, use it immediately
            if len(ql) == 1:
                return ql[0]
            # More than one – pick by tradingClass heuristics
            for c in ql:
                if c.tradingClass == template.symbol:
                    return c
            return ql[0]
    except Exception:
        # qualification can raise when template is too fuzzy – fall through
        pass

    # --- slow path: reqContractDetails --------------------------------------------------
    cds = ib.reqContractDetails(template)
    if not cds:
        return None
    if len(cds) == 1:
        return cds[0].contract
    for cd in cds:
        if cd.contract.tradingClass == template.symbol:
            return cd.contract
    return cds[0].contract


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

    Supported hint formats:
    • exact ``YYYYMMDD`` → use if available
    • ``YYYYMM`` prefix → choose 3rd Friday of that month, else first expiry
    • month name/abbr (``july``) → same logic across any year
    • ``day month`` (``26 jun``/``jun 26``/``26/06``) → nearest expiry on or
      after that date
    • otherwise falls back to :func:`choose_expiry`.
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
    # day + month input
    def parse_day_month(h: str) -> tuple[int, int] | tuple[None, None]:
        fmts = ["%d %b", "%d %B", "%b %d", "%B %d", "%d/%m", "%d-%m", "%d.%m"]
        for fmt in fmts:
            try:
                dt = datetime.strptime(h, fmt)
                return dt.day, dt.month
            except ValueError:
                continue
        return None, None

    day, month = parse_day_month(hint)
    if day:
        first_year = datetime.strptime(expirations[0], "%Y%m%d").year
        candidate = date(first_year, month, day)
        for e in expirations:
            ed = datetime.strptime(e, "%Y%m%d").date()
            if ed >= candidate:
                return e
        candidate = date(first_year + 1, month, day)
        for e in expirations:
            ed = datetime.strptime(e, "%Y%m%d").date()
            if ed >= candidate:
                return e

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


# ──────── per-symbol expiry map parser ────────
def parse_symbol_expiries(spec: str) -> dict[str, list[str]]:
    """Parse 'TSLA:20250620,20250703;AAPL:20250620' style strings."""
    mapping: dict[str, list[str]] = {}
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            sym, exp_str = part.split(":", 1)
            expiries = [e.strip() for e in exp_str.split(",") if e.strip()]
        else:
            sym, expiries = part, []
        sym = sym.strip().upper()
        if not sym:
            continue
        mapping.setdefault(sym, []).extend(expiries)
    return mapping


def prompt_symbol_expiries() -> dict[str, list[str]]:
    """Interactively build a symbol→expiry map."""
    result: dict[str, list[str]] = {}
    while True:
        symbol = input("Symbol (blank to finish): ").strip()
        if not symbol:
            break
        symbol = symbol.upper()
        exp = input(
            f"Expiries for {symbol} (comma-separated, blank for auto): "
        ).strip()
        entry = parse_symbol_expiries(f"{symbol}:{exp}" if exp else symbol)
        for sym, vals in entry.items():
            result.setdefault(sym, []).extend(vals)
    return result


# ─────────── Black–Scholes fallback (for delayed feeds) ───────────


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


def _attr(tk, field):
    """Return a numeric ticker attribute or NaN if unavailable."""
    val = getattr(tk, field, np.nan)
    return np.nan if val in (None, -1) else val


# ── helper: robust open‑interest getter ──


def fetch_yf_open_interest(symbol: str, expiry: str) -> dict[tuple[float, str], int]:
    """
    Return {(strike, right): open_interest} for a given symbol‑expiry pair
    using yfinance.

    yfinance expects the expiry in 'YYYY‑MM‑DD' format, whereas IB returns
    'YYYYMMDD'.  We normalise the string first, then attempt to fetch.
    Falls back to {} on any error or if the dataframe is empty.
    """
    # normalise expiry to YYYY‑MM‑DD for yfinance
    if len(expiry) == 8 and expiry.isdigit():
        expiry_fmt = f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:]}"
    else:
        expiry_fmt = expiry

    try:
        oc = yf.Ticker(symbol).option_chain(expiry_fmt)
    except Exception as e:  # pragma: no cover – network failures
        logger.debug("yfinance OI fetch fail %s %s: %s", symbol, expiry_fmt, e)
        return {}

    mapping: dict[tuple[float, str], int] = {}
    for right, df in (("C", oc.calls), ("P", oc.puts)):
        if getattr(df, "empty", True):
            continue
        for _, row in df[["strike", "openInterest"]].dropna().iterrows():
            try:
                mapping[(float(row["strike"]), right)] = int(row["openInterest"])
            except Exception:
                continue
    return mapping


def _wait_for_snapshots(ib: IB, snaps: list[tuple], timeout=8.0):
    """Wait until all tickers have a non-None timestamp or timeout."""
    end = time.time() + timeout
    while time.time() < end:
        if all(getattr(tk, "time", None) for _, tk in snaps):
            break
        time.sleep(0.25)


def _wait_attr(tk, field: str, timeout: float = 2.0) -> None:
    """Poll ticker until attribute present or timeout."""
    end = time.time() + timeout
    while time.time() < end:
        val = getattr(tk, field, None)
        if val not in (None, -1):
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

    # choose the chain with the richest strike list (the “real” OPRA feed),
    # fall back to the first one if all are empty
    chain = max(
        (c for c in chains if c.strikes),
        key=lambda c: len(c.strikes),
        default=chains[0],
    )
    logger.info(
        "Using chain %s (exchange=%s, strikes=%d, expiries=%d)",
        getattr(chain, "tradingClass", "<n/a>"),
        getattr(chain, "exchange", "<n/a>"),
        len(chain.strikes),
        len(chain.expirations),
    )
    expiry = pick_expiry_with_hint(sorted(chain.expirations), expiry_hint)

    # always fetch open interest from Yahoo Finance
    yf_open_interest = fetch_yf_open_interest(symbol, expiry)

    # trading class
    root_tc = (
        chain.tradingClasses[0]
        if getattr(chain, "tradingClasses", None)
        else getattr(chain, "tradingClass", symbol) or symbol
    )
    use_trading_class = bool(root_tc and root_tc != symbol)

    # ── spot price and ±20 strikes ────────────────────────────────
    strikes_all = sorted(chain.strikes)

    spot_tk = ib.reqMktData(stk, "", True, False)
    ib.sleep(0.5)

    spot = _safe_spot(ib, stk, spot_tk)

    if spot_tk.contract:
        ib.cancelMktData(spot_tk.contract)

    if np.isnan(spot):
        logger.warning("Could not obtain reliable spot price – using full strike list")
        strikes = strikes_all
    else:
        # if spot lies outside the strike lattice (e.g. right after a split) warn & keep full list
        if spot < strikes_all[0] or spot > strikes_all[-1]:
            logger.warning(
                "Spot %.2f is outside strike range %s‑%s (possible recent split); using full strike list.",
                spot,
                strikes_all[0],
                strikes_all[-1],
            )
            strikes = strikes_all
        else:
            idx = bisect_left(strikes_all, spot)
            start = max(0, idx - 20)
            end = min(len(strikes_all), idx + 21)
            strikes = strikes_all[start:end]
            logger.info(
                "Spot %.2f → selected %d strikes (%s‑%s)",
                spot,
                len(strikes),
                strikes[0],
                strikes[-1],
            )

    # ── build contracts and resolve ambiguities ──
    raw_templates = [
        Option(
            symbol,
            expiry,
            strike,
            right,
            exchange="SMART",
            currency="USD",
            tradingClass=root_tc,  # <‑‑ add this
        )
        for strike in strikes
        for right in ("C", "P")
    ]

    contracts: list[Option] = []
    for tmpl in raw_templates:
        # --- first try with tradingClass as provided (root_tc) -----------------
        c = _resolve_contract(ib, tmpl)

        # --- fallback #1: strip tradingClass if first attempt failed -----------
        if c is None and use_trading_class:
            tmpl_no_tc = Option(
                tmpl.symbol,
                tmpl.lastTradeDateOrContractMonth,
                tmpl.strike,
                tmpl.right,
                exchange=tmpl.exchange,
                currency=tmpl.currency,
            )
            c = _resolve_contract(ib, tmpl_no_tc)

        # --- fallback #2: use the underlying symbol as tradingClass ------------
        if c is None and use_trading_class and root_tc != symbol:
            tmpl_sym_tc = Option(
                tmpl.symbol,
                tmpl.lastTradeDateOrContractMonth,
                tmpl.strike,
                tmpl.right,
                exchange=tmpl.exchange,
                currency=tmpl.currency,
                tradingClass=symbol,  # use the underlying itself
            )
            c = _resolve_contract(ib, tmpl_sym_tc)

        if c:
            contracts.append(c)

    if not contracts:
        raise RuntimeError(
            "No option contracts qualified for the chosen strikes / expiry"
        )

    # stream market data (need streaming for generic-tick 101)
    snapshots = [
        (
            c,
            ib.reqMktData(
                c,
                "",  # let IB decide tick types; avoids eid errors
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

    # ── one-shot snapshot fallback for missing price/IV ──
    for con, tk in snapshots:
        price_missing = (tk.bid in (None, -1)) and (tk.last in (None, -1))
        iv_missing = math.isnan(_g(tk, "impliedVolatility"))
        if price_missing or iv_missing:
            snap = ib.reqMktData(
                con, "", True, False
            )  # snapshot: genericTickList must be empty
            ib.sleep(0.35)
            for fld in ("bid", "ask", "last", "close", "impliedVolatility"):
                val = getattr(snap, fld, None)
                if val not in (None, -1):
                    setattr(tk, fld, val)
            if getattr(snap, "modelGreeks", None):
                tk.modelGreeks = snap.modelGreeks
            # Copy volume if present
            if getattr(snap, "volume", None) not in (None, -1):
                tk.volume = snap.volume
            if snap.contract:
                ib.cancelMktData(snap.contract)

    # build rows
    ts_local = datetime.now(ZoneInfo("Europe/Istanbul"))
    ts = ts_local.isoformat()
    rows = []
    for con, tk in snapshots:
        oi_attr = "callOpenInterest" if con.right == "C" else "putOpenInterest"
        iv_val = _g(tk, "impliedVolatility")
        delta_val = _g(tk, "delta")
        gamma_val = _g(tk, "gamma")
        vega_val = _g(tk, "vega")
        theta_val = _g(tk, "theta")

        # Black-Scholes fallback if still NaN
        if any(np.isnan(x) for x in (delta_val, gamma_val, vega_val, theta_val)):
            if spot and iv_val and not np.isnan(iv_val):
                exp_dt = datetime.strptime(expiry, "%Y%m%d").replace(
                    tzinfo=timezone.utc
                )
                T = max(
                    (exp_dt - datetime.now(timezone.utc)).total_seconds()
                    / (365 * 24 * 3600),
                    1 / (365 * 24),
                )
                bs = bs_greeks(spot, con.strike, T, 0.01, iv_val, con.right == "C")
                delta_val = bs["delta"] if np.isnan(delta_val) else delta_val
                gamma_val = bs["gamma"] if np.isnan(gamma_val) else gamma_val
                vega_val = bs["vega"] if np.isnan(vega_val) else vega_val
                theta_val = bs["theta"] if np.isnan(theta_val) else theta_val

        mid_price = np.nan if any(np.isnan([tk.bid, tk.ask])) else (tk.bid + tk.ask) / 2

        rows.append(
            {
                "timestamp": ts,
                "symbol": symbol,
                "spot": spot,
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
                "open_interest": yf_open_interest.get((con.strike, con.right), np.nan),
                "volume": _attr(tk, "volume"),
            }
        )

    df = (
        pd.DataFrame(rows).sort_values(["right", "strike"]).reset_index(drop=True)
        if rows
        else pd.DataFrame()
    )

    return df

