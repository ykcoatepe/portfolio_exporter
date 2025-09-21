#!/usr/bin/env python3


from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from typing import Iterable, List, Tuple
from typing import Optional

import pandas as pd

try:  # optional dependencies
    import xlsxwriter  # type: ignore
except Exception:  # pragma: no cover - optional
    xlsxwriter = None  # type: ignore

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
TIME_TAG = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%H%M")
OUTPUT_DIR = Path(
    "/Users/yordamkocatepe/Library/Mobile Documents/" "com~apple~CloudDocs/Downloads"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7496, 5  # dedicated clientId (set 7497 for paper)


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

    filt = ExecutionFilter(time=start.strftime("%Y%m%d 00:00:00"))
    exec_details = ib.reqExecutions(filt)  # synchronous; returns list immediately
    ib.sleep(0.3)  # brief pause so CommissionReport callbacks arrive
    ib.commissionReportEvent -= _comm

    execs = [(det.contract, det.execution) for det in exec_details]

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


def save_csvs(
    trades: Iterable[Trade],
    open_orders: Iterable[OpenOrder],
    start: date,
    end: date,
) -> Tuple[Path, Path]:
    ts = TIME_TAG
    base = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}_{ts}"

    # trades file
    trades_file = OUTPUT_DIR / f"trades_{base}.csv"
    with open(trades_file, "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["# Orders Made"])  # user‑friendly banner
        wr.writerow(Trade.__annotations__.keys())
        for t in trades:
            wr.writerow([getattr(t, f) for f in Trade.__annotations__])

    # open orders file
    oo_file = OUTPUT_DIR / f"open_orders_{base}.csv"
    with open(oo_file, "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["# Open Orders"])  # section banner
        wr.writerow(OpenOrder.__annotations__.keys())
        for o in open_orders:
            wr.writerow([getattr(o, f) for f in OpenOrder.__annotations__])

    return trades_file, oo_file


# Helper for Excel export: auto-fit columns
def _auto_fit_columns(
    df: pd.DataFrame, writer: pd.ExcelWriter, sheet_name: str
) -> None:
    """
    Auto‑adjust column widths based on the longest value in each column.
    """
    worksheet = writer.sheets[sheet_name]
    for i, col in enumerate(df.columns):
        # find length of the column header and the longest cell content
        max_len = max(
            df[col].astype(str).map(len).max(),
            len(col),
        )
        # Add a little extra space
        worksheet.set_column(i, i, max_len + 2)


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


# Save Excel workbook with trades and open orders
def save_excel(
    trades: Iterable[Trade],
    open_orders: Iterable[OpenOrder],
    start: date,
    end: date,
) -> Optional[Path]:
    """
    Save trades and open orders to a nicely formatted Excel workbook that is
    easier to read than raw CSVs. Returns the path to the created workbook,
    or None if both data sets are empty.
    """
    trades = list(trades)
    open_orders = list(open_orders)
    if not trades and not open_orders:
        return None

    ts = TIME_TAG
    base = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}_{ts}"
    excel_path = OUTPUT_DIR / f"trades_report_{base}.xlsx"

    # Convert dataclass lists to DataFrames
    df_trades = pd.DataFrame([t.__dict__ for t in trades])
    df_open = pd.DataFrame([o.__dict__ for o in open_orders])

    # ── ensure Excel gets timezone‑naive datetimes ─────────────────────────────
    if "datetime" in df_trades.columns:
        # pandas raises if we call tz_localize(None) on a naive column, so check dtype first
        dt_ser = pd.to_datetime(df_trades["datetime"], errors="coerce")
        if isinstance(dt_ser.dtype, pd.DatetimeTZDtype):
            dt_ser = dt_ser.dt.tz_localize(None)
        df_trades["datetime"] = dt_ser

    if "combo_legs" in df_trades.columns:
        df_trades["combo_legs"] = df_trades["combo_legs"].apply(
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

    # Re‑order / hide columns for readability
    trade_cols_preferred = [
        "datetime",
        "symbol",
        "sec_type",
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
        "exchange",
        "combo_legs",
        "order_id",
        "exec_id",
    ]
    df_trades = df_trades[[c for c in trade_cols_preferred if c in df_trades.columns]]

    open_cols_preferred = [
        "symbol",
        "sec_type",
        "side",
        "total_qty",
        "lmt_price",
        "aux_price",
        "status",
        "filled",
        "remaining",
        "expiry",
        "strike",
        "right",
        "combo_legs",
        "order_type",
        "order_id",
    ]
    df_open = df_open[[c for c in open_cols_preferred if c in df_open.columns]]

    if "combo_legs" in df_open.columns:
        df_open["combo_legs"] = df_open["combo_legs"].apply(
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

    with pd.ExcelWriter(
        excel_path, engine="xlsxwriter", datetime_format="yyyy-mm-dd hh:mm:ss"
    ) as writer:
        if not df_trades.empty:
            df_trades.to_excel(writer, sheet_name="Trades", index=False)
            _auto_fit_columns(df_trades, writer, "Trades")

            # --- summary sheet, grouped by symbol -------------
            summary = (
                df_trades.groupby("symbol")
                .agg(
                    trades_count=("exec_id", "count"),
                    total_qty=("qty", "sum"),
                    realized_pnl=("realized_pnl", "sum"),
                )
                .reset_index()
                .sort_values("realized_pnl", ascending=False)
            )
            summary.to_excel(writer, sheet_name="Summary", index=False)
            _auto_fit_columns(summary, writer, "Summary")

        if not df_open.empty:
            df_open.to_excel(writer, sheet_name="OpenOrders", index=False)
            _auto_fit_columns(df_open, writer, "OpenOrders")

    return excel_path


def save_pdf(
    trades: Iterable[Trade], open_orders: Iterable[OpenOrder], start: date, end: date
) -> Optional[Path]:
    trades = list(trades)
    open_orders = list(open_orders)
    if not trades and not open_orders:
        return None

    ts = TIME_TAG
    base = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}_{ts}"
    pdf_path = OUTPUT_DIR / f"trades_report_{base}.pdf"

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


def main() -> None:
    p = argparse.ArgumentParser(description="Filter trade history")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--today", action="store_true", help="Trades for today")
    g.add_argument("--yesterday", action="store_true", help="Trades for yesterday")
    g.add_argument("--week", action="store_true", help="Week to date")
    g.add_argument("--phrase", help="Custom date phrase, e.g. 'June 2024'")
    g.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--ibport", type=int, help="Override API port (default 7496; use 7497 for paper)")
    p.add_argument("--cid", type=int, help="Override IB clientId (default 5)")
    out_grp = p.add_mutually_exclusive_group()
    out_grp.add_argument(
        "--excel",
        action="store_true",
        help="Save output as an Excel workbook instead of CSV.",
    )
    out_grp.add_argument(
        "--pdf",
        action="store_true",
        help="Save output as a PDF report instead of CSV.",
    )

    args = p.parse_args()

    if not args.excel and not args.pdf:
        try:
            choice = (
                input("Select output format [csv / excel / pdf] (default csv): ")
                .strip()
                .lower()
            )
        except EOFError:
            choice = ""
        if choice in {"excel", "xlsx"}:
            args.excel = True
        elif choice == "pdf":
            args.pdf = True

    global IB_PORT, IB_CID
    if args.ibport:
        IB_PORT = args.ibport
    if args.cid:
        IB_CID = args.cid

    if args.today:
        start, end = date_range_from_phrase("today")
    elif args.yesterday:
        start, end = date_range_from_phrase("yesterday")
    elif args.week:
        start, end = date_range_from_phrase("week")
    elif args.phrase:
        start, end = date_range_from_phrase(args.phrase)
    elif args.start:
        s = datetime.fromisoformat(args.start).date()
        e = datetime.fromisoformat(args.end).date() if args.end else s
        start, end = s, e
    else:
        # No CLI flags – fall back to interactive prompt
        start, end = prompt_date_range()

    trades, open_orders = fetch_trades_ib(start, end)
    if not trades and not open_orders:
        print("⚠ No executions or open orders retrieved.")
        return

    trades = filter_trades(trades, start, end)

    if args.excel:
        excel_path = save_excel(trades, open_orders, start, end)
        if excel_path:
            print(f"\u2705  Saved Excel report to {excel_path}")
    elif args.pdf:
        pdf_path = save_pdf(trades, open_orders, start, end)
        if pdf_path:
            print(f"\u2705  Saved PDF report to {pdf_path}")
    else:
        trade_path, oo_path = save_csvs(trades, open_orders, start, end)
        print(f"\u2705  Saved {len(trades)} trades to {trade_path}")
        print(f"\u2705  Saved {len(open_orders)} open orders to {oo_path}")


if __name__ == "__main__":
    main()
