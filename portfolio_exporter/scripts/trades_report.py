#!/usr/bin/env python3


from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import os
import argparse
import json

from portfolio_exporter.core.config import settings

from typing import Iterable, List, Tuple
from typing import Optional

import pandas as pd
import numpy as np
import logging

from portfolio_exporter.core import combo as combo_core
from portfolio_exporter.core import io as io_core
from portfolio_exporter.core import config as config_core

# Reuse enrichment from portfolio_greeks to keep behavior identical
try:
    from portfolio_exporter.scripts.portfolio_greeks import (  # type: ignore
        _enrich_combo_strikes as _enrich_combo_strikes_greeks,
    )
except Exception:  # pragma: no cover - defensive import fallback
    _enrich_combo_strikes_greeks = None  # type: ignore

logger = logging.getLogger(__name__)

try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer,
        PageBreak,
    )
    from reportlab.lib.styles import getSampleStyleSheet
except Exception:  # pragma: no cover - optional
    (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer,
        PageBreak,
        getSampleStyleSheet,
        colors,
        letter,
        landscape,
    ) = (None,) * 10
import calendar

try:  # optional dependency
    from ib_insync import IB, ExecutionFilter  # type: ignore
except Exception:  # pragma: no cover - optional
    IB = None  # type: ignore
    ExecutionFilter = None  # type: ignore

# Give the user a clear hint if ib_insync is missing
if IB is None:
    print(
        "❌  ib_insync library not found. Install with:\n"
        "    pip install ib_insync\n"
        "and ensure the Interactive Brokers TWS or IB Gateway is running with "
        "API enabled."
    )


LIQ_MAP = {1: "Added", 2: "Removed", 3: "RoutedOut", 4: "Auction"}


# ───── Lightweight executions loader & action classifier ─────
def _load_trades() -> pd.DataFrame | None:
    """Fetch executed trades from IBKR.

    Raises
    ------
    RuntimeError
        If ib_insync is not available or IB API cannot be used.

    Returns
    -------
    DataFrame | None
        DataFrame of executions. Tests may monkeypatch this function and
        return a prebuilt DataFrame.
    """
    if IB is None or ExecutionFilter is None:
        raise RuntimeError(
            "❌ ib_insync library not found or IB ExecutionFilter unavailable. "
            "Install with: pip install ib_insync and ensure the IB Gateway/TWS is running with API enabled."
        )

    start, end = prompt_date_range()
    trades, _open_orders = fetch_trades_ib(start, end)
    trades = filter_trades(trades, start, end)
    df = pd.DataFrame([t.__dict__ for t in trades])
    if df.empty:
        print("⚠ No executions found for that period.")
        return pd.DataFrame()
    return df


def _load_open_orders() -> pd.DataFrame:
    from ib_insync import IB

    ib = IB()
    try:
        ib.connect("127.0.0.1", 7497, clientId=19, timeout=5)
    except Exception as exc:  # pragma: no cover - connection optional
        logger.error(f"IBKR connect failed: {exc}")
        return pd.DataFrame()

    rows = []
    for o in ib.openOrders():
        c = o.contract
        rows.append(
            {
                "PermId": o.permId,
                "OrderId": o.orderId,
                "symbol": c.symbol,
                "secType": c.secType,
                "Side": o.action.upper(),
                "Qty": o.totalQuantity,
                "Price": getattr(o, "lmtPrice", np.nan),
                "OrderRef": o.orderRef or "",
                "Liquidation": 0,
                "lastLiquidity": 0,
                "Action": "Open",
            }
        )
    ib.disconnect()
    return pd.DataFrame(rows)


def _classify(row: pd.Series) -> str:
    sec = row.get("secType", "")
    side = row.get("Side", "")
    liq = int(row.get("Liquidation", 0))
    lastliq = int(row.get("lastLiquidity", 0))
    ref = (row.get("OrderRef") or "").upper()

    if sec == "BAG":
        return "Combo"
    if "ROLL" in ref:
        return "Roll"
    if liq > 0 or lastliq in {2, 4}:
        return "Close"
    return "Buy" if side == "BOT" else "Sell"


@dataclass
class Trade:
    # execution identifiers
    exec_id: str
    perm_id: int
    order_id: int

    # contract fields
    symbol: str
    sec_type: str
    currency: str
    expiry: str | None
    strike: float | None
    right: str | None
    multiplier: int | None
    exchange: str
    primary_exchange: str | None
    trading_class: str | None
    combo_legs: List[dict] | None

    # fill details
    datetime: datetime
    side: str
    qty: int
    price: float
    avg_price: float
    cum_qty: int
    last_liquidity: str

    # commission / pnl
    commission: float | None
    commission_currency: str | None
    realized_pnl: float | None
    account: str | None
    model_code: str | None
    order_ref: str | None


@dataclass
class OpenOrder:
    order_id: int
    perm_id: int
    symbol: str
    sec_type: str
    currency: str
    expiry: str | None
    strike: float | None
    right: str | None
    combo_legs: List[dict] | None
    side: str
    total_qty: int
    lmt_price: float | None
    aux_price: float | None
    tif: str | None
    order_type: str
    algo_strategy: str | None
    status: str
    filled: int
    remaining: int
    account: str | None
    order_ref: str | None


# ───────────────────────── CONFIG ──────────────────────────
# Use Türkiye local time (Europe/Istanbul) for timestamp tags
IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7497, 5  # dedicated clientId


MONTH_MAP = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTH_MAP.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})


def date_range_from_phrase(phrase: str, ref: date | None = None) -> Tuple[date, date]:
    phrase = phrase.strip().lower()
    ref = ref or date.today()

    if phrase in {"today"}:
        return ref, ref
    if phrase == "yesterday":
        y = ref - timedelta(days=1)
        return y, y
    if phrase in {"week", "week to date", "week-to-date", "wtd"}:
        start = ref - timedelta(days=ref.weekday())
        return start, ref
    if re.fullmatch(r"\d{4}", phrase):
        year = int(phrase)
        return date(year, 1, 1), date(year, 12, 31)

    m = re.fullmatch(r"([a-zA-Z]+)\s*(\d{4})?", phrase)
    if m and m.group(1).lower() in MONTH_MAP:
        month = MONTH_MAP[m.group(1).lower()]
        year = int(m.group(2)) if m.group(2) else ref.year
        last = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last)

    dt = pd.to_datetime(phrase, errors="coerce")
    if pd.notnull(dt):
        d = dt.date()
        return d, d
    raise ValueError(f"Unrecognised date phrase: {phrase}")


# ─────────────────── interactive date‑range prompt ───────────────────
def prompt_date_range() -> Tuple[date, date]:
    """
    Ask the user which range to pull (today / yesterday / week / custom).
    Returns a (start, end) date tuple.
    """
    print("\nSelect trade‑log range:")
    print("  1  Today")
    print("  2  Yesterday")
    print("  3  Week‑to‑date")
    print("  4  Custom (YYYY‑MM‑DD or phrase e.g. 'June 2024')")
    while True:
        choice = input("Enter choice [1‑4]: ").strip()
        if choice == "1":
            return date_range_from_phrase("today")
        if choice == "2":
            return date_range_from_phrase("yesterday")
        if choice == "3":
            return date_range_from_phrase("week")
        if choice == "4":
            phrase = input("Enter date / phrase: ").strip()
            try:
                return date_range_from_phrase(phrase)
            except ValueError as e:
                print(f"  ⚠ {e}")
                continue
        print("  ⚠ Invalid choice; try again.")


def filter_trades(trades: Iterable[Trade], start: date, end: date) -> List[Trade]:
    return [t for t in trades if start <= t.datetime.date() <= end]


def fetch_trades_ib(start: date, end: date) -> Tuple[List[Trade], List[OpenOrder]]:
    """
    Return (trades, open_orders) within [start, end] inclusive.
    Uses execDetails / commissionReport / openOrder callbacks.
    """
    if IB is None or ExecutionFilter is None:
        return [], []

    ib = IB()

    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CID, timeout=10)
    except Exception as exc:
        print(
            f"❌  Unable to connect to IBKR at {IB_HOST}:{IB_PORT} "
            f"(clientId={IB_CID}).\n"
            f"    Exception: {exc}"
        )
        return [], []

    # --- Capture executions & commission reports ------------------------------
    comm_map: dict[str, "CommissionReport"] = {}

    # CommissionReport only comes via callback; cache them by execId
    def _comm(*args):
        report = args[-1]  # CommissionReport is always last arg
        comm_map[report.execId] = report

    ib.commissionReportEvent += _comm

    all_execs: list["ExecutionDetail"] = []
    day = start
    while day <= end:
        next_day = day + timedelta(days=1)
        filt = ExecutionFilter(
            time=day.strftime("%Y%m%d 00:00:00"), clientId=0, acctCode=""
        )
        all_execs.extend(ib.reqExecutions(filt))
        day = next_day
    print(f"[INFO] pulled {len(all_execs)} executions between {start} and {end}")
    ib.sleep(0.3)  # brief pause so CommissionReport callbacks arrive
    ib.commissionReportEvent -= _comm

    execs = [(det.contract, det.execution) for det in all_execs]

    # --- Build Trade objects ---------------------------------------------------
    trades: List[Trade] = []
    for contract, ex in execs:
        exec_dt = pd.to_datetime(ex.time).to_pydatetime()
        if not (start <= exec_dt.date() <= end):
            continue

        # ensure contract is qualified for full fields
        if not contract.conId:
            (qualified,) = ib.qualifyContracts(contract)
            contract = qualified

        combo_legs_data = []
        if contract.secType == "BAG" and contract.comboLegs:
            from ib_insync import Contract

            for leg in contract.comboLegs:
                # For combo legs, we need to qualify each leg's contract to get details like symbol, expiry, strike, right
                leg_contract = ib.qualifyContracts(
                    Contract(conId=leg.conId, exchange=leg.exchange)
                )[0]
                combo_legs_data.append(
                    {
                        "symbol": leg_contract.symbol,
                        "sec_type": leg_contract.secType,
                        "expiry": getattr(
                            leg_contract, "lastTradeDateOrContractMonth", None
                        ),
                        "strike": getattr(leg_contract, "strike", None),
                        "right": getattr(leg_contract, "right", None),
                        "ratio": leg.ratio,
                        "action": leg.action,
                        "exchange": leg.exchange,
                    }
                )

        comm = comm_map.get(ex.execId, None)
        trades.append(
            Trade(
                exec_id=ex.execId,
                perm_id=ex.permId,
                order_id=ex.orderId,
                symbol=contract.symbol,
                sec_type=contract.secType,
                currency=contract.currency,
                expiry=getattr(contract, "lastTradeDateOrContractMonth", None),
                strike=getattr(contract, "strike", None),
                right=getattr(contract, "right", None),
                multiplier=(
                    int(contract.multiplier)
                    if getattr(contract, "multiplier", None)
                    else None
                ),
                exchange=ex.exchange,
                primary_exchange=getattr(contract, "primaryExchange", None),
                trading_class=getattr(contract, "tradingClass", None),
                combo_legs=combo_legs_data if combo_legs_data else None,
                datetime=exec_dt,
                side="BUY" if ex.side.upper() == "BOT" else "SELL",
                qty=int(ex.shares),
                price=ex.price,
                avg_price=ex.avgPrice,
                cum_qty=ex.cumQty,
                last_liquidity=LIQ_MAP.get(ex.lastLiquidity, str(ex.lastLiquidity)),
                commission=comm.commission if comm else None,
                commission_currency=comm.currency if comm else None,
                realized_pnl=comm.realizedPNL if comm else None,
                account=ex.acctNumber,
                model_code=ex.modelCode,
                order_ref=ex.orderRef,
            )
        )

    # --- Capture open orders ---------------------------------------------------
    ib.reqAllOpenOrders()
    ib.sleep(1.5)  # allow gateway to populate the cache; was 0.6
    open_trades_snapshot: List["Trade"] = ib.openTrades()

    open_orders: List[OpenOrder] = []
    for tr in open_trades_snapshot:
        c = tr.contract
        o = tr.order
        status = tr.orderStatus

        combo_legs_data = []
        if c.secType == "BAG" and c.comboLegs:
            from ib_insync import Contract

            for leg in c.comboLegs:
                leg_contract = ib.qualifyContracts(
                    Contract(conId=leg.conId, exchange=leg.exchange)
                )[0]
                combo_legs_data.append(
                    {
                        "symbol": leg_contract.symbol,
                        "sec_type": leg_contract.secType,
                        "expiry": getattr(
                            leg_contract, "lastTradeDateOrContractMonth", None
                        ),
                        "strike": getattr(leg_contract, "strike", None),
                        "right": getattr(leg_contract, "right", None),
                        "ratio": leg.ratio,
                        "action": leg.action,
                        "exchange": leg.exchange,
                    }
                )

        open_orders.append(
            OpenOrder(
                order_id=o.orderId,
                perm_id=o.permId,
                symbol=c.symbol,
                sec_type=c.secType,
                currency=c.currency,
                expiry=getattr(c, "lastTradeDateOrContractMonth", None),
                strike=getattr(c, "strike", None),
                right=getattr(c, "right", None),
                combo_legs=combo_legs_data if combo_legs_data else None,
                side=o.action,
                total_qty=o.totalQuantity,
                lmt_price=o.lmtPrice if o.orderType in {"LMT", "LIT", "REL"} else None,
                aux_price=o.auxPrice if hasattr(o, "auxPrice") else None,
                tif=o.tif,
                order_type=o.orderType,
                algo_strategy=o.algoStrategy,
                status=status.status if status else "Unknown",
                filled=status.filled if status else 0,
                remaining=status.remaining if status else o.totalQuantity,
                account=o.account,
                order_ref=o.orderRef,
            )
        )

    ib.disconnect()
    return trades, open_orders


# Helper for PDF tables: size columns based on content length
def _calc_table_col_widths(
    data: list[list],
    page_width: float,
    fixed_idx: int | None = None,
    fixed_pct: float = 0.40,
) -> list[float]:
    """
    Return a list of column widths (in points) that add up to page_width.

    * data       — table data including header row (list of rows)
    * page_width — available width in the PDF page (points)
    * fixed_idx  — if not None, reserve `fixed_pct` of page_width for this column
    * fixed_pct  — fraction of page_width for the fixed column (default 40 %)
    """
    ncols = len(data[0])
    # maximum visible string length per column (header + cells)
    max_lens = [max(len(str(row[i])) for row in data) for i in range(ncols)]

    if fixed_idx is not None:
        fixed_w = page_width * fixed_pct
        flexible_w = page_width - fixed_w
        total_len = sum(max_lens[i] for i in range(ncols) if i != fixed_idx) or 1
        col_widths = [
            fixed_w if i == fixed_idx else flexible_w * max_lens[i] / total_len
            for i in range(ncols)
        ]
    else:
        total_len = sum(max_lens) or 1
        col_widths = [page_width * l / total_len for l in max_lens]

    return col_widths


# Save PDF report with trades and open orders
def save_pdf(
    trades: Iterable[Trade],
    open_orders: Iterable[OpenOrder],
    start: date,
    end: date,
    out_path: Path,
) -> Optional[Path]:
    trades = list(trades)
    open_orders = list(open_orders)
    if not trades and not open_orders:
        return None

    pdf_path = Path(out_path)

    df_trades = pd.DataFrame([t.__dict__ for t in trades])
    df_open = pd.DataFrame([o.__dict__ for o in open_orders])

    elements = []
    styles = getSampleStyleSheet()
    hdr_style = styles["Heading2"]
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=landscape(letter),
        rightMargin=18,
        leftMargin=18,
        topMargin=18,
        bottomMargin=18,
    )
    # ---- compute usable page width and prettify numeric columns ----
    page_width = landscape(letter)[0] - doc.leftMargin - doc.rightMargin

    df_trades_fmt = df_trades.copy()
    if not df_trades_fmt.empty:
        # -- strip internal identifier fields; they clutter the PDF --
        drop_trade_cols = ["exec_id", "perm_id", "order_id", "model_code", "order_ref"]
        df_trades_fmt.drop(
            columns=[c for c in drop_trade_cols if c in df_trades_fmt.columns],
            inplace=True,
            errors="ignore",
        )
        num_cols = df_trades_fmt.select_dtypes(include=[float, int]).columns
        for col in num_cols:
            df_trades_fmt[col] = df_trades_fmt[col].map(
                lambda x: f"{x:,.3f}" if isinstance(x, (float, int)) else x
            )
        if "combo_legs" in df_trades_fmt.columns:
            df_trades_fmt["combo_legs"] = df_trades_fmt["combo_legs"].apply(
                lambda x: (
                    "\n".join(
                        [
                            f"{leg['ratio']}x {leg['action']} {leg['symbol']} ({leg['sec_type']}) "
                            f"Exp: {leg['expiry'] or 'N/A'}, Strike: {leg['strike'] or 'N/A'}, Right: {leg['right'] or 'N/A'}"
                            for leg in x
                        ]
                    )
                    if x
                    else None
                )
            )

    df_open_fmt = df_open.copy()
    if not df_open_fmt.empty:
        # -- strip ID-style columns from open orders as well --
        drop_open_cols = ["order_id", "perm_id"]
        df_open_fmt.drop(
            columns=[c for c in drop_open_cols if c in df_open_fmt.columns],
            inplace=True,
            errors="ignore",
        )
        num_cols_open = df_open_fmt.select_dtypes(include=[float, int]).columns
        for col in num_cols_open:
            df_open_fmt[col] = df_open_fmt[col].map(
                lambda x: f"{x:,.3f}" if isinstance(x, (float, int)) else x
            )
        if "combo_legs" in df_open_fmt.columns:
            df_open_fmt["combo_legs"] = df_open_fmt["combo_legs"].apply(
                lambda x: (
                    "\n".join(
                        [
                            f"{leg['ratio']}x {leg['action']} {leg['symbol']} ({leg['sec_type']}) "
                            f"Exp: {leg['expiry'] or 'N/A'}, Strike: {leg['strike'] or 'N/A'}, Right: {leg['right'] or 'N/A'}"
                            for leg in x
                        ]
                    )
                    if x
                    else None
                )
            )

    # ---- TRADES TABLE (consolidated for readability) ----
    if not df_trades_fmt.empty:
        elements.append(Paragraph("Trades Executed", hdr_style))
        elements.append(Spacer(1, 6))

        trade_cols = [
            "datetime",
            "symbol",
            "side",
            "qty",
            "price",
            "avg_price",
            "realized_pnl",
            "commission",
            "currency",
            "expiry",
            "strike",
            "right",
            "combo_legs",
        ]
        trade_cols = [c for c in trade_cols if c in df_trades_fmt.columns]

        data = [trade_cols] + df_trades_fmt[trade_cols].values.tolist()

        combo_idx = (
            trade_cols.index("combo_legs") if "combo_legs" in trade_cols else None
        )
        col_widths = _calc_table_col_widths(data, page_width, fixed_idx=combo_idx)

        tbl = Table(data, repeatRows=1, colWidths=col_widths, hAlign="LEFT")
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("ALIGN", (0, 1), (-1, -1), "RIGHT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.whitesmoke, colors.lightgrey],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                ]
            )
        )
        elements.append(tbl)
        elements.append(PageBreak())

    # ---- OPEN ORDERS TABLE (consolidated) ----
    if not df_open_fmt.empty:
        elements.append(Paragraph("Open Orders", hdr_style))
        elements.append(Spacer(1, 6))

        open_cols = [
            "symbol",
            "side",
            "total_qty",
            "status",
            "filled",
            "remaining",
            "lmt_price",
            "aux_price",
            "expiry",
            "strike",
            "right",
            "combo_legs",
        ]
        open_cols = [c for c in open_cols if c in df_open_fmt.columns]

        data = [open_cols] + df_open_fmt[open_cols].values.tolist()

        combo_idx = open_cols.index("combo_legs") if "combo_legs" in open_cols else None
        col_widths = _calc_table_col_widths(data, page_width, fixed_idx=combo_idx)

        tbl = Table(data, repeatRows=1, colWidths=col_widths, hAlign="LEFT")
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.darkgreen),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("ALIGN", (0, 1), (-1, -1), "RIGHT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.whitesmoke, colors.lightgrey],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                ]
            )
        )
        elements.append(tbl)

    doc.build(elements)
    return pdf_path


def run(
    fmt: str = "csv",
    show_actions: bool = False,
    include_open: bool = True,
    return_df: bool = False,
) -> pd.DataFrame | None:
    """Generate trades report and export in desired format."""
    trades = _load_trades()
    if trades is None:
        return None

    df = trades.copy()
    if include_open:
        open_df = _load_open_orders()
        df = pd.concat([df, open_df], ignore_index=True, sort=False)

    if df.empty:
        print("⚠️ No trades found for the specified date range; no report generated.")
        return None
    if show_actions:
        df["Action"] = df.apply(
            lambda r: r["Action"] if r.get("Action") == "Open" else _classify(r),
            axis=1,
        )

    from portfolio_exporter.core.io import save

    # Timestamped filename for easier tracking and to avoid overwrites
    date_tag = datetime.now(ZoneInfo(settings.timezone)).strftime("%Y%m%d_%H%M")
    path = save(df, f"trades_report_{date_tag}", fmt, settings.output_dir)
    print(f"✅ Trades report exported → {path}")
    if return_df:
        return df
    return None


# ───────────────────────── combos from trades/open orders ─────────────────────────
def _standardize_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()
    # common aliases
    rename = {}
    for a, b in (
        ("sec_type", "secType"),
        ("underlying", "symbol"),
        ("permId", "perm_id"),
        ("orderId", "order_id"),
    ):
        if a in d.columns and b not in d.columns:
            rename[a] = b
    if rename:
        d = d.rename(columns=rename)

    # unify side text
    def _norm_side(x: object) -> str:
        s = str(x).strip().upper()
        if s in {"BOT", "BUY"}:
            return "BUY"
        if s in {"SLD", "SELL"}:
            return "SELL"
        return s

    for c in ("Side", "side"):
        if c in d.columns:
            d[c] = d[c].apply(_norm_side)

    # datetime parsing
    for c in ("datetime", "timestamp", "time"):
        if c in d.columns:
            try:
                d[c] = pd.to_datetime(d[c], errors="coerce")
            except Exception:
                pass
            if c != "datetime" and "datetime" not in d.columns:
                d["datetime"] = d[c]
            break

    # numeric coercions
    for c in ("qty", "Qty", "total_qty"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ("strike", "price", "lmt_price", "aux_price", "multiplier"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")

    # right normalization
    if "right" in d.columns:
        d["right"] = d["right"].astype(str).str.upper().map({"CALL": "C", "PUT": "P", "C": "C", "P": "P"}).fillna("")

    # expiry pass-through
    for c in ("expiry", "lastTradeDateOrContractMonth"):
        if c in d.columns and "expiry" not in d.columns:
            d["expiry"] = d[c]
            break

    # secType pass-through
    for c in ("secType", "sec_type"):
        if c in d.columns and "secType" not in d.columns:
            d["secType"] = d[c]
            break

    # conId pass-through
    for c in ("conId", "conid"):
        if c in d.columns and "conId" not in d.columns:
            d["conId"] = d[c]
            break
    if "conId" in d.columns:
        try:
            d["conId"] = pd.to_numeric(d["conId"], errors="coerce").astype("Int64")
        except Exception:
            pass

    return d


def _build_positions_like_df(execs: pd.DataFrame, opens: pd.DataFrame | None = None) -> pd.DataFrame:
    e = _standardize_cols(execs)
    o = _standardize_cols(opens) if isinstance(opens, pd.DataFrame) else pd.DataFrame()
    frames = [x for x in (e, o) if x is not None and not x.empty]
    if not frames:
        return pd.DataFrame(columns=["underlying", "expiry", "right", "strike", "qty", "secType", "conId", "multiplier", "price", "order_id", "perm_id", "datetime"])
    df = pd.concat(frames, ignore_index=True, sort=False)

    # pick qty, side, price
    qty = (
        df["qty"]
        if "qty" in df.columns
        else df["Qty"] if "Qty" in df.columns
        else df["total_qty"] if "total_qty" in df.columns
        else pd.Series([np.nan] * len(df))
    )
    side = df["Side"] if "Side" in df.columns else df["side"] if "side" in df.columns else pd.Series([""] * len(df))
    # signed qty: BUY +, SELL -
    sign = side.apply(lambda s: 1 if str(s).upper() == "BUY" else (-1 if str(s).upper() == "SELL" else 1))
    qty_signed = pd.to_numeric(qty, errors="coerce").fillna(0).astype(float) * sign
    price = (
        df["price"]
        if "price" in df.columns
        else df["lmt_price"] if "lmt_price" in df.columns
        else pd.Series([np.nan] * len(df))
    )
    # multiplier default per secType
    mult = df.get("multiplier")
    if mult is None or mult.isna().all():
        mult = df.get("secType").map({"OPT": 100, "FOP": 100, "STK": 1, "ETF": 1}).fillna(100)

    out = pd.DataFrame(
        {
            "underlying": df.get("symbol"),
            "expiry": df.get("expiry", ""),
            "right": df.get("right", ""),
            "strike": df.get("strike", np.nan),
            "qty": qty_signed,
            "secType": df.get("secType"),
            "conId": df.get("conId"),
            "multiplier": mult,
            "price": price,
            "order_id": df.get("order_id"),
            "perm_id": df.get("perm_id"),
            "datetime": df.get("datetime"),
        }
    )
    # type coercions
    out["strike"] = pd.to_numeric(out["strike"], errors="coerce")
    out["qty"] = pd.to_numeric(out["qty"], errors="coerce")
    try:
        out["conId"] = pd.to_numeric(out["conId"], errors="coerce").astype("Int64")
    except Exception:
        pass
    try:
        out["multiplier"] = pd.to_numeric(out["multiplier"], errors="coerce").fillna(100).astype(int)
    except Exception:
        out["multiplier"] = 100
    # normalize right
    if "right" in out.columns:
        out["right"] = out["right"].astype(str).str.upper().replace({"CALL": "C", "PUT": "P", "NAN": ""})
        out.loc[~out["right"].isin(["C", "P"]) , "right"] = ""
    return out


def _detect_and_enrich_trades_combos(execs_df: pd.DataFrame, opens_df: pd.DataFrame | None = None) -> pd.DataFrame:
    # Build positions-like df
    pos_like = _build_positions_like_df(execs_df, opens_df)
    if pos_like is None or pos_like.empty:
        return pd.DataFrame(columns=[
            "underlying","expiry","structure","structure_label","type","legs","legs_n","width","strikes","call_strikes","put_strikes","call_count","put_count","has_stock_leg","when","order_ids","net_qty","net_credit_debit",
        ])

    # Group by underlying (simple clustering per Phase 1)
    combos_rows: list[pd.DataFrame] = []
    meta_rows: list[dict] = []
    for u, g in pos_like.groupby("underlying"):
        # Detect combos for this underlying
        detected = combo_core.detect_from_positions(g)
        if detected is None or detected.empty:
            continue
        detected = detected.copy()
        # attach per-underlying meta
        when_val = None
        try:
            when_val = pd.to_datetime(g.get("datetime"), errors="coerce").min()
        except Exception:
            when_val = pd.NaT
        order_ids = []
        for c in ("order_id", "perm_id"):
            if c in g.columns:
                order_ids.extend(sorted(set([str(x) for x in g[c].dropna().tolist()])))
        # net qty and net credit/debit
        net_qty = float(pd.to_numeric(g.get("qty"), errors="coerce").fillna(0).sum())
        try:
            ncd = (-pd.to_numeric(g.get("price"), errors="coerce") * pd.to_numeric(g.get("qty"), errors="coerce") * pd.to_numeric(g.get("multiplier"), errors="coerce")).sum()
            net_cd = float(ncd) if pd.notna(ncd) else np.nan
        except Exception:
            net_cd = np.nan

        detected["when"] = when_val
        detected["order_ids"] = ",".join(sorted(set(order_ids))) if order_ids else ""
        detected["net_qty"] = net_qty
        detected["net_credit_debit"] = net_cd
        combos_rows.append(detected)

    if not combos_rows:
        combos_df = pd.DataFrame()
    else:
        combos_df = pd.concat(combos_rows, ignore_index=True, sort=False)

    # Enrichment – prefer positions mapping
    if _enrich_combo_strikes_greeks is not None:
        try:
            combos_df = _enrich_combo_strikes_greeks(combos_df, positions_df=pos_like)
        except Exception:
            pass
    else:
        # Minimal fallback enrichment if portfolio_greeks helper is unavailable
        combos_df = _enrich_combo_strikes_fallback(combos_df, pos_like)

    # Normalize legs to a JSON list string and recompute legs_n
    try:
        def _to_json_list(v):
            if isinstance(v, list):
                return json.dumps(v)
            if isinstance(v, str) and v.strip().startswith("["):
                return v
            return json.dumps([])
        if "legs" in combos_df.columns:
            combos_df["legs"] = combos_df["legs"].apply(_to_json_list)
            # legs_n must reflect parsed length
            def _len_json(s):
                try:
                    return len(json.loads(s)) if isinstance(s, str) else 0
                except Exception:
                    return 0
            combos_df["legs_n"] = combos_df["legs"].apply(_len_json).astype("Int64")
    except Exception:
        pass

    return combos_df


def _save_trades_combos(df: pd.DataFrame, fmt: str = "csv") -> Path:
    # Drop debug/helper columns from save output
    out = df.drop(columns=["__db_legs_detail", "__strike_source", "__healed_legs"], errors="ignore")
    return io_core.save(out, "trades_combos", fmt, config_core.settings.output_dir)


def _enrich_combo_strikes_fallback(combos_df: pd.DataFrame, positions_df: pd.DataFrame | None) -> pd.DataFrame:
    df = combos_df.copy() if isinstance(combos_df, pd.DataFrame) else pd.DataFrame()
    if df.empty:
        for c in ("strikes", "call_strikes", "put_strikes"):
            df[c] = ""
        for c in ("call_count", "put_count"):
            df[c] = 0
        df["has_stock_leg"] = False
        return df

    # Build positions lookup by conId
    if positions_df is None or positions_df.empty:
        pos_lookup = pd.DataFrame(columns=["right", "strike", "secType"]).set_index(pd.Index([], name="conid"))
    else:
        p = positions_df.copy()
        if "conId" in p.columns and "conid" not in p.columns:
            p = p.rename(columns={"conId": "conid"})
        if "conid" not in p.columns:
            p["conid"] = pd.NA
        for c in ("right", "strike", "secType"):
            if c not in p.columns:
                p[c] = pd.NA
        p["conid"] = pd.to_numeric(p["conid"], errors="coerce")
        p = p.dropna(subset=["conid"]).copy()
        p["conid"] = p["conid"].astype(int)
        p["strike"] = pd.to_numeric(p["strike"], errors="coerce")
        pos_lookup = p.set_index("conid")[ ["right", "strike", "secType"] ]

    df = df.copy()
    df["strikes"] = ""
    df["call_strikes"] = ""
    df["put_strikes"] = ""
    df["call_count"] = 0
    df["put_count"] = 0
    df["has_stock_leg"] = False
    df["__strike_source"] = ""

    fmt = lambda x: ("{:.1f}".format(float(x)).rstrip("0").rstrip("."))

    import ast
    res = {k: [] for k in ["strikes","call_strikes","put_strikes","call_count","put_count","has_stock_leg","__strike_source"]}

    def _collect(legs_val):
        leg_ids, leg_dicts = [], []
        def _from_seq(seq):
            for x in seq:
                if isinstance(x, (int,)) or (isinstance(x, str) and str(x).lstrip("-").isdigit()):
                    try:
                        leg_ids.append(int(x))
                    except Exception:
                        pass
                elif isinstance(x, dict):
                    leg_dicts.append(x)
                elif isinstance(x, (list, tuple)) and len(x) >= 2:
                    try:
                        right = str(x[0]).upper()
                    except Exception:
                        right = ""
                    try:
                        strike = float(x[1]) if x[1] is not None else None
                    except Exception:
                        strike = None
                    leg_dicts.append({"right": right if right in ("C","P") else "", "strike": strike, "secType": None})
        if isinstance(legs_val, list):
            _from_seq(legs_val)
        elif isinstance(legs_val, str) and legs_val.strip().startswith("["):
            try:
                parsed = ast.literal_eval(legs_val)
                if isinstance(parsed, (list, tuple)):
                    _from_seq(parsed)
            except Exception:
                pass
        return leg_ids, leg_dicts

    for _, row in df.iterrows():
        leg_ids, leg_dicts = _collect(row.get("legs"))
        call_k, put_k = set(), set()
        call_n = 0
        put_n = 0
        stock_flag = False
        source_tag = ""
        for cid in leg_ids:
            if cid in pos_lookup.index:
                rec = pos_lookup.loc[cid]
                if isinstance(rec, pd.DataFrame):
                    rec = rec.iloc[0]
                r = (str(rec.get("right")) if pd.notna(rec.get("right")) else "").upper()
                k = rec.get("strike")
                st = str(rec.get("secType")) if pd.notna(rec.get("secType")) else ""
                if r == "C":
                    call_n += 1
                    if pd.notna(k):
                        try:
                            call_k.add(float(k))
                        except Exception:
                            pass
                elif r == "P":
                    put_n += 1
                    if pd.notna(k):
                        try:
                            put_k.add(float(k))
                        except Exception:
                            pass
                if st == "STK" or r == "":
                    stock_flag = True
                source_tag = source_tag or "pos"
        # Also include dict-style legs if present (already normalized above)
        for ent in leg_dicts:
            r = str(ent.get("right") or "").upper()
            try:
                k = float(ent.get("strike")) if ent.get("strike") is not None else None
            except Exception:
                k = None
            st = str(ent.get("secType") or "")
            if st == "STK" or r == "":
                stock_flag = True
            if r == "C":
                call_n += 1
                if k is not None:
                    call_k.add(float(k))
            elif r == "P":
                put_n += 1
                if k is not None:
                    put_k.add(float(k))

        all_k = sorted(call_k.union(put_k))
        res["strikes"].append("/".join(fmt(x) for x in all_k) if all_k else "")
        res["call_strikes"].append("/".join(fmt(x) for x in sorted(call_k)) if call_k else "")
        res["put_strikes"].append("/".join(fmt(x) for x in sorted(put_k)) if put_k else "")
        res["call_count"].append(int(call_n))
        res["put_count"].append(int(put_n))
        res["has_stock_leg"].append(bool(stock_flag))
        res["__strike_source"].append(source_tag)

    for k, v in res.items():
        df[k] = v

    # Optional debug
    try:
        if os.getenv("PE_DEBUG_COMBOS") == "1":
            io_core.save(df.copy(), "combos_enriched_debug", "csv", config_core.settings.output_dir)
            df = df.drop(columns=["__strike_source"], errors="ignore")
    except Exception:
        pass
    return df


def _run_cli() -> int:
    parser = argparse.ArgumentParser(description="Trades report and combos export")
    parser.add_argument("--executions-csv", dest="exec_csv", help="Path to offline executions CSV", default=None)
    parser.add_argument("--no-pretty", action="store_true", help="Disable pretty/TTY output", default=False)
    parser.add_argument("--debug-combos", action="store_true", help="Force combos debug artifacts (equivalent to PE_DEBUG_COMBOS=1)", default=False)
    args = parser.parse_args()

    if args.debug_combos:
        os.environ["PE_DEBUG_COMBOS"] = "1"

    df_exec = None
    df_open = None
    if args.exec_csv:
        try:
            df_exec = pd.read_csv(args.exec_csv)
        except Exception as exc:
            print(f"❌ Failed to read executions CSV: {exc}")
            return 2
    else:
        # Fallback to interactive IBKR pull
        t = _load_trades()
        if t is None:
            return 1
        df_exec = t
        try:
            df_open = _load_open_orders()
        except Exception:
            df_open = None

    # Save the combined trades/open report as before (additive only)
    try:
        df_all = df_exec.copy()
        if isinstance(df_open, pd.DataFrame) and not df_open.empty:
            df_all = pd.concat([df_all, df_open], ignore_index=True, sort=False)
        date_tag = datetime.now(ZoneInfo(settings.timezone)).strftime("%Y%m%d_%H%M")
        io_core.save(df_all, f"trades_report_{date_tag}", "csv", config_core.settings.output_dir)
    except Exception:
        pass

    # Detect + enrich combos from executions/open orders
    combos_df = _detect_and_enrich_trades_combos(df_exec, df_open)
    path = _save_trades_combos(combos_df, fmt="csv")
    print(f"✅ Trades combos exported → {path}")

    # Write debug combos CSV when requested (handled inside enrichment via env)
    # no-pretty is respected by doing nothing extra when printing
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by CLI tests
    raise SystemExit(_run_cli())
