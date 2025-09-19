#!/usr/bin/env python3
"""
daily_pulse.py – Yordam's pre‑market overview
Run at 07:00 Europe/Istanbul. Produces an Excel workbook in iCloud/Downloads.
"""

import asyncio
import csv
import logging
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf  # pip install yfinance

from portfolio_exporter.core import io
from portfolio_exporter.core import ui as core_ui
from utils.progress import iter_progress

run_with_spinner = core_ui.run_with_spinner
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter  # PDF output (landscape added)
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

# ── Silence noisy libraries ────────────────────────────────────────────────
logging.getLogger("ib_insync").setLevel(logging.CRITICAL)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# --- Interactive Brokers live API ---
# pip install ib_insync (requires TWS or IB Gateway running with API enabled)
from ib_insync import IB

# --------------------------------------------------------------------------- #
# CONFIG – edit these two blocks only                                         #
# --------------------------------------------------------------------------- #

# 1.  Where your *latest* IB CSV lives (auto‑export or manual upload).
IB_CSV = Path("/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/IB/Latest/")

# 2.  Macro/technical watch‑list & indicators
MARKET_OVERVIEW = {
    #   Ticker   : Friendly name
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "IWM": "Russell 2000",
    "VIX": "VIX Index",
    "DXY": "US Dollar",
    "TLT": "US 20Y Bond",
    "IEF": "US 7‑10Y Bond",
    "GC=F": "Gold Futures",
    "CL=F": "WTI Oil",
    "BTC-USD": "Bitcoin",
}

INDICATORS = [
    "pct_change",
    "sma20",
    "ema20",
    "rsi14",
    "macd",
    "macd_signal",
    "atr14",
    "bb_upper",
    "bb_lower",
    "real_vol_30",
]

# --------------------------------------------------------------------------- #
# HELPER FUNCTIONS                                                            #
# --------------------------------------------------------------------------- #


def _ensure_event_loop() -> asyncio.AbstractEventLoop:
    """Ensure ib_insync has an event loop even on Python 3.11+."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


def load_ib_positions_ib(
    host: str = "127.0.0.1",
    port: int = 7496,
    client_id: int = 999,
) -> pd.DataFrame:
    """
    Pull current portfolio positions directly from Interactive Brokers via
    the TWS / IB‑Gateway API (ib_insync wrapper).

    Columns returned: symbol · quantity · cost basis · mark price ·
    market_value · unrealized_pnl
    """
    _ensure_event_loop()  # ib_insync expects a live asyncio loop on modern Python
    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id)
        # suppress per‑contract error spam from IB
        ib.errorEvent += lambda *a, **k: None
    except Exception as e:
        raise ConnectionError(f"❌ Cannot connect to IB API at {host}:{port}  →  {e}") from e

    positions = ib.positions()
    if not positions:
        ib.disconnect()
        raise RuntimeError(
            "API returned no positions. Confirm account is logged in and the API user has permissions."
        )

    contracts = [p.contract for p in positions]
    # Request real‑time market data in a single call
    tickers = ib.reqTickers(*contracts)

    # Build a quick {conId: last_price} map
    price_map = {}
    for t in tickers:
        # fall back to mid‑point if last==0
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

    ib.disconnect()
    return df


def fetch_ohlc(tickers, days_back=60) -> pd.DataFrame:
    """Download daily OHLCV plus today’s pre‑market quote."""
    end = datetime.now(UTC)
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


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """(Same logic as your original, condensed & vectorised)"""
    df = df.sort_values(["ticker", "date"]).copy()
    grp = df.groupby("ticker", group_keys=False)

    df["pct_change"] = grp["close"].pct_change(fill_method=None)
    df["sma20"] = grp["close"].transform(lambda s: s.rolling(20).mean())
    df["ema20"] = grp["close"].transform(lambda s: s.ewm(span=20).mean())

    # RSI14
    delta = grp["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["rsi14"] = 100 - 100 / (1 + rs)

    # MACD
    ema12 = grp["close"].transform(lambda s: s.ewm(span=12).mean())
    ema26 = grp["close"].transform(lambda s: s.ewm(span=26).mean())
    df["macd"] = ema12 - ema26
    df["macd_signal"] = grp["macd"].transform(lambda s: s.ewm(span=9).mean())

    # ATR14
    tr = (
        (df["high"] - df["low"])
        .abs()
        .to_frame("hl")
        .join((df["high"] - grp["close"].shift()).abs().to_frame("hc"))
        .join((df["low"] - grp["close"].shift()).abs().to_frame("lc"))
        .max(axis=1)
    )
    df["atr14"] = grp.apply(lambda g: tr.loc[g.index].rolling(14).mean(), include_groups=False)

    # Bollinger
    m20 = df["sma20"]
    std20 = grp["close"].transform(lambda s: s.rolling(20).std())
    df["bb_upper"] = m20 + 2 * std20
    df["bb_lower"] = m20 - 2 * std20

    df["vwap"] = (df["close"] * df["volume"]).groupby(df["ticker"]).cumsum() / df["volume"].groupby(
        df["ticker"]
    ).cumsum()

    # Realised vol 30d
    df["real_vol_30"] = grp["pct_change"].transform(lambda s: s.rolling(30).std() * (252**0.5))
    return df


def last_row(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values("date").groupby("ticker").tail(1).set_index("ticker")


def generate_report(df: pd.DataFrame, output_path: str, fmt: str = "csv") -> None:
    """Write the latest metrics for each ticker to ``output_path``."""
    latest = df.sort_values("date").groupby("ticker", as_index=False).tail(1).set_index("ticker", drop=True)

    cols = [
        "close",
        "pct_change",
        "sma20",
        "ema20",
        "atr14",
        "rsi14",
        "macd",
        "macd_signal",
        "bb_upper",
        "bb_lower",
        "vwap",
        "real_vol_30",
    ]

    cols = [c for c in cols if c in latest.columns]
    latest = latest[cols].round(3)

    if fmt == "excel":
        with pd.ExcelWriter(output_path, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
            latest.reset_index().to_excel(writer, sheet_name="Pulse", index=False, float_format="%.3f")
    elif fmt == "pdf":
        if SimpleDocTemplate is None:
            raise RuntimeError("reportlab is required for PDF output")
        rows = [latest.reset_index().columns.tolist()] + latest.reset_index().values.tolist()
        doc = SimpleDocTemplate(
            output_path,
            pagesize=landscape(letter),
            rightMargin=18,
            leftMargin=18,
            topMargin=18,
            bottomMargin=18,
        )
        table = Table(rows, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                ]
            )
        )
        doc.build([table])
    else:
        latest.to_csv(output_path, quoting=csv.QUOTE_MINIMAL, float_format="%.3f")


# --------------------------------------------------------------------------- #
# MAIN                                                                        #
# --------------------------------------------------------------------------- #


def run(fmt: str = "csv") -> None:
    filetype = fmt if fmt in {"xlsx", "csv", "flatcsv", "pdf", "txt"} else "csv"

    # 1. positions
    pos = load_ib_positions_ib()  # live connection to IB/TWS

    # --- tidy numeric precision ------------------------------------------------
    num_cols_pos = ["cost basis", "mark price", "market_value", "unrealized_pnl"]
    pos[num_cols_pos] = pos[num_cols_pos].round(3)
    pos = pos.rename(columns={"symbol": "ticker"})

    # 2. technical data
    tickers = list(MARKET_OVERVIEW.keys()) + pos["ticker"].unique().tolist()
    ohlc = run_with_spinner("Fetching price data…", fetch_ohlc, tickers)
    tech = compute_indicators(ohlc)
    tech_last = last_row(tech)[INDICATORS].round(3)

    # 3. macro overview (price & % chg vs yesterday close)
    macro_px = tech_last[["pct_change"]].copy()
    macro_px.columns = ["pct_change"]
    macro_px.insert(0, "close", last_row(tech)["close"].round(3))
    macro_px.insert(0, "name", [MARKET_OVERVIEW.get(t, t) for t in tech_last.index])
    macro_px.index.name = "ticker"

    # round & make % column easier to read
    macro_px["close"] = macro_px["close"].round(3)
    macro_px["pct_change"] = (macro_px["pct_change"] * 100).round(3)

    # ------------------------------------------------------------------- #
    # Save results                                                        #
    # ------------------------------------------------------------------- #
    io.save(tech_last.reset_index(), "daily_pulse", filetype)
