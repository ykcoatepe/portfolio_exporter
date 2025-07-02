from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import pandas as pd


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Convert index to ``date`` and sort."""
    new_index = pd.to_datetime(df.index).date
    df = df.copy()
    df.index = new_index
    return df.sort_index()


def _filter_range(
    df: pd.DataFrame, start: Optional[str | date], end: Optional[str | date]
) -> pd.DataFrame:
    """Return rows within ``start`` and ``end`` (inclusive)."""
    if isinstance(start, str):
        start = datetime.strptime(start, "%Y-%m-%d").date()
    if isinstance(end, str):
        end = datetime.strptime(end, "%Y-%m-%d").date()
    start = start or df.index.min()
    end = end or df.index.max()
    mask = (df.index >= start) & (df.index <= end)
    return df.loc[mask]
