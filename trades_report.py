#!/usr/bin/env python3
"""Trade history filter with convenient date phrases.

If no ``--file`` is supplied, trade executions are fetched from the
connected IBKR session.
"""

from __future__ import annotations

import argparse
import calendar
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from pathlib import Path
from typing import Iterable, List, Tuple

import pandas as pd

# optional ib_insync integration
try:  # pragma: no cover - optional dependency
    from ib_insync import ExecutionFilter, IB

    IB_AVAILABLE = True
except Exception:  # pragma: no cover - missing dep
    IB_AVAILABLE = False
    ExecutionFilter = None  # type: ignore
    IB = None  # type: ignore

IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7497, 12


@dataclass
class Trade:
    date: date
    ticker: str
    side: str
    qty: int
    price: float


MONTH_MAP = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTH_MAP.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})


def _load_csv(path: str) -> List[Trade]:
    df = pd.read_csv(path, parse_dates=["date"])
    return [
        Trade(r.date.date(), r.ticker, r.side, int(r.qty), float(r.price))
        for r in df.itertuples(index=False)
    ]


def fetch_ib_trades(start: date, end: date) -> List[Trade]:
    """Return executions between start and end dates from IBKR."""
    if not IB_AVAILABLE:
        return []
    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CID, timeout=5)
    except Exception:
        return []
    filt = ExecutionFilter(time=start.strftime("%Y%m%d %H:%M:%S"))
    fills = ib.reqExecutions(filt)
    ib.disconnect()
    trades = []
    for fill in fills:
        d = fill.execution.time.date()
        if start <= d <= end:
            trades.append(
                Trade(
                    d,
                    fill.contract.symbol,
                    fill.execution.side.upper(),
                    int(fill.execution.shares),
                    float(fill.execution.price),
                )
            )
    return trades


def load_trades(source: str | None, start: date, end: date) -> List[Trade]:
    if source and Path(source).exists():
        return _load_csv(source)
    ib_trades = fetch_ib_trades(start, end)
    return ib_trades


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


def main() -> None:
    p = argparse.ArgumentParser(description="Filter trade history")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--today", action="store_true", help="Trades for today")
    g.add_argument("--yesterday", action="store_true", help="Trades for yesterday")
    g.add_argument("--week", action="store_true", help="Week to date")
    g.add_argument("--phrase", help="Custom date phrase, e.g. 'June 2024'")
    g.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--file", help="CSV file (default: fetch from IBKR)")
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

    trades = load_trades(args.file, start, end)
    selected = filter_trades(trades, start, end)
    writer = csv.writer(sys.stdout)
    writer.writerow(["date", "ticker", "side", "qty", "price"])
    for t in selected:
        writer.writerow([t.date.isoformat(), t.ticker, t.side, t.qty, f"{t.price:.2f}"])


if __name__ == "__main__":
    import sys

    main()
