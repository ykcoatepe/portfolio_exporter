#!/usr/bin/env python3


from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from portfolio_exporter.core.config import settings

from typing import Iterable, List, Tuple
from typing import Optional

import pandas as pd
import numpy as np
import logging

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
