from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional, Tuple

import pandas as pd


@dataclass
class Trade:
    exec_id: str
    perm_id: int
    order_id: int
    symbol: str
    sec_type: str
    currency: str
    expiry: Optional[str]
    strike: Optional[float]
    right: Optional[str]
    multiplier: Optional[str]
    exchange: str
    primary_exchange: Optional[str]
    trading_class: Optional[str]
    datetime: pd.Timestamp
    side: str
    qty: float
    price: float
    avg_price: float
    cum_qty: float
    last_liquidity: str
    commission: Optional[float]
    commission_currency: Optional[str]
    realized_pnl: Optional[float]
    account: Optional[str]
    model_code: Optional[str]
    order_ref: Optional[str]
    combo_legs: Optional[list]


@dataclass
class OpenOrder:
    order_id: int
    perm_id: int
    symbol: str
    sec_type: str
    currency: str
    expiry: Optional[str]
    strike: Optional[float]
    right: Optional[str]
    combo_legs: Optional[list]
    side: str
    total_qty: float
    lmt_price: float
    aux_price: float
    tif: str
    order_type: str
    algo_strategy: Optional[str]
    status: str
    filled: float
    remaining: float
    account: str
    order_ref: Optional[str]


def date_range_from_phrase(phrase: str, ref: date) -> Tuple[date, date]:
    phrase = phrase.lower()
    if phrase == "today":
        return ref, ref
    if phrase == "yesterday":
        d = ref - timedelta(days=1)
        return d, d
    if phrase == "week":
        start = ref - timedelta(days=ref.weekday())
        return start, ref
    if phrase.isdigit() and len(phrase) == 4:
        year = int(phrase)
        return date(year, 1, 1), date(year, 12, 31)
    try:
        month = datetime.strptime(phrase, "%B").month
    except ValueError:
        month = datetime.strptime(phrase, "%b").month
    year = ref.year if month <= ref.month else ref.year - 1
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def filter_trades(trades: Iterable[Trade], start: date, end: date) -> List[Trade]:
    return [t for t in trades if start <= t.datetime.date() <= end]
