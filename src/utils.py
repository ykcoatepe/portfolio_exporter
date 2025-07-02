from __future__ import annotations

import logging
from typing import Iterable, Iterator, List
import pandas as pd
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.theme import Theme

from . import data_fetching

_PASTEL_THEME = Theme(
    {
        "progress.spinner": "#a5d8ff",
        "progress.description": "#ffd6a5",
        "bar.back": "#e0e0e0",
    }
)

_console = Console(theme=_PASTEL_THEME, force_terminal=True)


def progress_bar(iterable: Iterable, description: str) -> Iterator:
    """Iterate with a pastel themed progress bar."""
    items = list(iterable)
    progress = Progress(
        SpinnerColumn(style="progress.spinner"),
        BarColumn(),
        TextColumn(description, style="progress.description"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=_console,
        transient=True,
    )
    with progress:
        task = progress.add_task(description, total=len(items))
        for item in items:
            yield item
            progress.advance(task)


def detect_combos(df: pd.DataFrame) -> pd.DataFrame:
    """Group multi-leg option combos into single rows."""
    if df.empty or "parentId" not in df.columns:
        return df
    combos = df.groupby(["underlying", "parentId"])
    combined = combos.agg(
        {
            "delta": "sum",
            "gamma": "sum",
            "vega": "sum",
            "theta": "sum",
            "rho": "sum",
            "position": "sum",
        }
    ).reset_index()
    combined["is_combo"] = combined.duplicated(["underlying", "parentId"], keep=False)
    return combined


def ib_first_quote(tickers: List[str], ib_timeout: float = 10.0) -> pd.DataFrame:
    """Fetch quotes from IB and fall back to yfinance on timeout."""
    try:
        ib = data_fetching.IB()
        ib.connect(
            data_fetching.IB_HOST,
            data_fetching.IB_PORT,
            data_fetching.IB_CLIENT_ID,
            timeout=ib_timeout,
        )
        contracts = [data_fetching.Stock(t, "SMART", "USD") for t in tickers]
        ib.qualifyContracts(*contracts)
        tks = ib.reqTickers(*contracts)
        ib.disconnect()
        rows = [
            {"ticker": t.contract.symbol, "last": t.last}
            for t in tks
            if t.last not in (None, -1)
        ]
        if rows:
            return pd.DataFrame(rows)
    except Exception as e:
        logging.getLogger(__name__).warning("IBKR quote fetch failed: %s", e)
    return data_fetching.fetch_yf_quotes(tickers)
