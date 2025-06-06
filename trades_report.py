#!/usr/bin/env python3


from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from typing import Iterable, List, Tuple

import pandas as pd
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
TIME_TAG = datetime.utcnow().strftime("%H%M")
OUTPUT_DIR = Path(
    "/Users/yordamkocatepe/Library/Mobile Documents/" "com~apple~CloudDocs/Downloads"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
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
    comm_map: dict[str, 'CommissionReport'] = {}

    # CommissionReport only comes via callback; cache them by execId
    def _comm(*args):
        report = args[-1]          # CommissionReport is always last arg
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
            qualified, = ib.qualifyContracts(contract)
            contract = qualified

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
                multiplier=int(contract.multiplier) if getattr(contract, "multiplier", None) else None,
                exchange=ex.exchange,
                primary_exchange=getattr(contract, "primaryExchange", None),
                trading_class=getattr(contract, "tradingClass", None),
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
    ib.sleep(0.6)  # allow gateway to populate the cache
    open_trades_snapshot: List['Trade'] = ib.openTrades()

    open_orders: List[OpenOrder] = []
    for tr in open_trades_snapshot:
        c = tr.contract
        o = tr.order
        status = tr.orderStatus
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
        wr.writerow(Trade.__annotations__.keys())
        for t in trades:
            wr.writerow([getattr(t, f) for f in Trade.__annotations__])

    # open orders file
    oo_file = OUTPUT_DIR / f"open_orders_{base}.csv"
    with open(oo_file, "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(OpenOrder.__annotations__.keys())
        for o in open_orders:
            wr.writerow([getattr(o, f) for f in OpenOrder.__annotations__])

    return trades_file, oo_file


def main() -> None:
    p = argparse.ArgumentParser(description="Filter trade history")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--today", action="store_true", help="Trades for today")
    g.add_argument("--yesterday", action="store_true", help="Trades for yesterday")
    g.add_argument("--week", action="store_true", help="Week to date")
    g.add_argument("--phrase", help="Custom date phrase, e.g. 'June 2024'")
    g.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--ibport", type=int, help="Override API port (default 7497)")
    p.add_argument("--cid", type=int, help="Override IB clientId (default 5)")

    args = p.parse_args()

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
    trade_path, oo_path = save_csvs(trades, open_orders, start, end)
    print(f"\u2705  Saved {len(trades)} trades to {trade_path}")
    print(f"\u2705  Saved {len(open_orders)} open orders to {oo_path}")


if __name__ == "__main__":
    main()
