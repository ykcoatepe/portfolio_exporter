#!/usr/bin/env python3


from __future__ import annotations

import argparse
import calendar
import csv
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from typing import Iterable, List, Tuple

import pandas as pd

try:  # optional dependency
    from ib_insync import IB, ExecutionFilter  # type: ignore
except Exception:  # pragma: no cover - optional
    IB = None  # type: ignore
    ExecutionFilter = None  # type: ignore


@dataclass
class Trade:
    date: date
    ticker: str
    side: str
    qty: int
    price: float


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


def filter_trades(trades: Iterable[Trade], start: date, end: date) -> List[Trade]:
    return [t for t in trades if start <= t.date <= end]


def fetch_trades_ib(start: date, end: date) -> List[Trade]:
    """Return trades between start and end dates from IBKR."""
    if IB is None or ExecutionFilter is None:
        return []
    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CID, timeout=5)
    except Exception:
        return []

    filt = ExecutionFilter(time=start.strftime("%Y%m%d %H:%M:%S"))
    details = ib.reqExecutions(filt)
    trades: List[Trade] = []
    for det in details:
        exec_time = pd.to_datetime(det.execution.time).to_pydatetime()
        d = exec_time.date()
        if not (start <= d <= end):
            continue
        side = "BUY" if det.execution.side.upper() == "BOT" else "SELL"
        trades.append(
            Trade(
                d,
                det.contract.symbol,
                side,
                int(det.execution.shares),
                det.execution.price,
            )
        )
    ib.disconnect()
    return trades


def save_csv(trades: Iterable[Trade], start: date, end: date) -> Path:
    out_name = f"trades_report_{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}_{TIME_TAG}.csv"
    out_path = OUTPUT_DIR / out_name
    with open(out_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["date", "ticker", "side", "qty", "price"])
        for t in trades:
            writer.writerow(
                [t.date.isoformat(), t.ticker, t.side, t.qty, f"{t.price:.2f}"]
            )
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description="Filter trade history")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--today", action="store_true", help="Trades for today")
    g.add_argument("--yesterday", action="store_true", help="Trades for yesterday")
    g.add_argument("--week", action="store_true", help="Week to date")
    g.add_argument("--phrase", help="Custom date phrase, e.g. 'June 2024'")
    g.add_argument("--start")
    p.add_argument("--end")

    args = p.parse_args()

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
        p.print_help()
        return

    trades = fetch_trades_ib(start, end)
    if not trades:
        print("No trades retrieved from IBKR.")
        return

    trades = filter_trades(trades, start, end)
    out_file = save_csv(trades, start, end)
    print(f"\u2705  Saved {len(trades)} trades to {out_file}")


if __name__ == "__main__":
    main()
