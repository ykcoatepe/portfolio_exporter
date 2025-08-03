from __future__ import annotations

import os
import sys
from typing import List

import pandas as pd
from rich.console import Console
from rich.live import Live
from rich.table import Table

from portfolio_exporter.core import chain as core_chain
from portfolio_exporter.core.ib import quote_stock
from portfolio_exporter.core.ui import render_chain


def _calc_strikes(symbol: str, width: int) -> List[float]:
    """Return a list of strikes around ATM using 5-point increments."""
    try:
        spot = quote_stock(symbol)["mid"]
    except Exception:
        spot = 0
    return [round((spot // 5 + i) * 5, 0) for i in range(-width, width + 1)]


def run(
    symbol: str | None = None,
    expiry: str | None = None,
    strikes: List[float] | None = None,
    width: int = 5,
) -> None:
    """Interactive Rich-based option-chain browser."""

    from portfolio_exporter.menus import pre as pre_menu

    console = Console()

    default_symbol = symbol or pre_menu.last_symbol.get()
    symbol = input(f"Symbol [{default_symbol}]: ").strip().upper() or default_symbol
    if not symbol:
        return
    pre_menu.last_symbol.value = symbol

    default_expiry = expiry or pre_menu.last_expiry.get()
    expiry = (
        input(f"Expiry (YYYY-MM-DD) [{default_expiry}]: ").strip() or default_expiry
    )
    if not expiry:
        return
    pre_menu.last_expiry.value = expiry

    from yfinance import Ticker

    all_exps: list[str] = []

    def _valid_expirations(sym: str) -> list[str]:
        nonlocal all_exps
        if all_exps:
            return all_exps
        all_exps = Ticker(sym).options
        return all_exps

    def _nearest(expiry_date: str) -> str:
        # if the requested expiry is not listed, pick the next later one
        exps = _valid_expirations(symbol)
        if not exps:
            return expiry_date
        if expiry_date in exps:
            return expiry_date
        for e in exps:
            if e > expiry_date:
                return e
        return exps[-1]  # fallback: last available

    def _fetch(cur_width: int, cur_expiry: str) -> pd.DataFrame:
        exp = _nearest(cur_expiry)
        use_strikes = (
            strikes if strikes is not None else _calc_strikes(symbol, cur_width)
        )
        return core_chain.fetch_chain(symbol, exp, use_strikes)

    df = _fetch(width, expiry)

    def _grid() -> Table:
        calls = df[df["right"] == "C"].sort_values("strike").reset_index(drop=True)
        puts = df[df["right"] == "P"].sort_values("strike").reset_index(drop=True)
        grid = Table.grid(expand=True)
        grid.add_row(
            render_chain(calls, console, width), render_chain(puts, console, width)
        )
        return grid

    interactive = sys.stdin.isatty() or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if not interactive:
        console.print(_grid())
        return

    cursor = 0
    marked: list[int] = []

    with Live(_grid(), console=console, refresh_per_second=2) as live:
        while True:
            cmd = input()
            if cmd == "q":
                break
            if cmd == "\x1b[A":
                cursor = max(0, cursor - 1)
            elif cmd == "\x1b[B":
                cursor = min(len(df) - 1, cursor + 1)
            elif cmd == "[":
                width = max(1, width - 2)
                df = _fetch(width, expiry)
            elif cmd == "]":
                width += 2
                df = _fetch(width, expiry)
            elif cmd == ">":
                expiry = (
                    (pd.to_datetime(expiry) + pd.Timedelta(weeks=1)).date().isoformat()
                )
                df = _fetch(width, expiry)
            elif cmd == "<":
                expiry = (
                    (pd.to_datetime(expiry) - pd.Timedelta(weeks=1)).date().isoformat()
                )
                df = _fetch(width, expiry)
            elif cmd == " ":
                if cursor not in marked:
                    marked.append(cursor)
            elif cmd == "b" and len(marked) >= 2:
                from portfolio_exporter.scripts import order_builder

                order_builder.run()
                marked.clear()
            live.update(_grid())
