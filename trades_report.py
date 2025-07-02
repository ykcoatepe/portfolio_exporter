from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from enum import Enum
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


class DateOption(Enum):
    """Predefined date range options for trade reports."""

    TODAY = "today"
    YESTERDAY = "yesterday"
    WEEK_TO_DATE = "week_to_date"
    CUSTOM = "custom"


def get_date_range(
    option: DateOption,
    ref: date | None = None,
    start: date | None = None,
    end: date | None = None,
) -> Tuple[date, date]:
    """Return ``(start, end)`` dates for the given ``option``."""

    ref = ref or date.today()

    if option is DateOption.TODAY:
        return ref, ref
    if option is DateOption.YESTERDAY:
        d = ref - timedelta(days=1)
        return d, d
    if option is DateOption.WEEK_TO_DATE:
        start_date = ref - timedelta(days=ref.weekday())
        return start_date, ref
    if option is DateOption.CUSTOM:
        if start is None or end is None:
            raise ValueError("start and end are required for custom range")
        return start, end
    raise ValueError(f"Unsupported option: {option}")


def date_range_from_phrase(phrase: str, ref: date) -> Tuple[date, date]:
    """Return a date range for ``phrase`` (deprecated)."""

    import warnings

    warnings.warn(
        "date_range_from_phrase is deprecated; use get_date_range instead",
        DeprecationWarning,
        stacklevel=2,
    )

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
    """Return trades with ``datetime`` between ``start`` and ``end`` (inclusive)."""

    return [t for t in trades if start <= t.datetime.date() <= end]


def generate_trade_report(
    trades: Iterable[Trade] | pd.DataFrame,
    open_orders: Iterable[OpenOrder] | pd.DataFrame,
    date_option: DateOption,
    start: date | None = None,
    end: date | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return trades and open orders dataframes for the selected range."""

    start_date, end_date = get_date_range(date_option, start=start, end=end)

    if isinstance(trades, pd.DataFrame):
        trades_df = trades.copy()
    else:
        trades_df = pd.DataFrame([asdict(t) for t in trades])

    if not trades_df.empty and not isinstance(
        trades_df.iloc[0]["datetime"], pd.Timestamp
    ):
        trades_df["datetime"] = pd.to_datetime(trades_df["datetime"])

    mask = trades_df["datetime"].dt.date.between(start_date, end_date)
    trades_df = trades_df.loc[mask].reset_index(drop=True)

    if isinstance(open_orders, pd.DataFrame):
        open_orders_df = open_orders.copy()
    else:
        open_orders_df = pd.DataFrame([asdict(o) for o in open_orders])

    return trades_df, open_orders_df
