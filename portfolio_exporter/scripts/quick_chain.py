from __future__ import annotations

import os
from portfolio_exporter.core.config import settings
import sys
from typing import List

import pandas as pd
import dateparser
from rich.console import Console
from rich.live import Live
from rich.table import Table

from portfolio_exporter.core import chain as core_chain
from portfolio_exporter.core.ib import quote_stock
from portfolio_exporter.core.ui import render_chain, run_with_spinner


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
    """Interactive Rich-based option-chain browser with natural-language expiry parsing."""

    from portfolio_exporter.menus import pre as pre_menu

    console = Console()

    default_symbol = symbol or pre_menu.last_symbol.get()
    # ─────────────────── input & defaults ────────────────────────────
    symbol = input(f"Symbol [{default_symbol}]: ").strip().upper() or default_symbol
    if not symbol:
        return
    pre_menu.last_symbol.value = symbol

    default_expiry = expiry or pre_menu.last_expiry.get()
    # ── natural‑language expiry parsing ──────────────────────────────
    if not expiry:
        exp_raw = (
            input(
                f"Expiry (YYYY-MM-DD, 'Aug 15', '+30d', etc.) [{default_expiry}]: "
            ).strip()
            or default_expiry
        )
    else:
        exp_raw = expiry
    parsed_exp = dateparser.parse(exp_raw, settings={"PREFER_DATES_FROM": "future"})
    if not parsed_exp:
        console.print(f"[red]Could not parse expiry '{exp_raw}'.")
        return
    expiry = parsed_exp.strftime("%Y-%m-%d")
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

    # ------------- CSV toggle (default = ON) -------------------------
    save_csv_env = os.getenv("PE_CHAIN_CSV", "1")  # allow override
    save_csv = save_csv_env not in {"0", "false", "no"}

    def _fetch(cur_width: int, cur_expiry: str) -> pd.DataFrame:
        exp = _nearest(cur_expiry)
        use_strikes = (
            strikes if strikes is not None else _calc_strikes(symbol, cur_width)
        )
        df = run_with_spinner(
            f"Fetching {symbol} {exp} …",
            core_chain.fetch_chain,
            symbol,
            exp,
            use_strikes,
        )
        # ── optional CSV export ──────────────────────────────────────
        if save_csv:
            # Same directory convention as the other scripts
            out_dir = os.getenv("PE_OUTPUT_DIR", settings.output_dir)
            os.makedirs(out_dir, exist_ok=True)
            csv_path = os.path.join(
                out_dir, f"chain_{symbol}_{exp.replace('-', '')}.csv"
            )
            df.to_csv(csv_path, index=False)
            console.print(f"[green]CSV saved → {csv_path}")
        return df

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

    # ----------- interactive loop (render + hot-keys) ----------------
    toggle_msg = "[yellow]↑/↓: navigate  [cyan]space[/cyan]: mark  [cyan]b[/cyan]: build  [cyan]c[/cyan]: toggle CSV export  [cyan]q[/cyan]: quit"
    console.print(toggle_msg)

    cursor = 0
    marked: list[int] = []

    with Live(_grid(), console=console, refresh_per_second=2) as live:
        while True:
            cmd = input()
            if cmd == "c":
                save_csv = not save_csv
                console.print(f"[yellow]CSV export {'ON' if save_csv else 'OFF'}")
                continue
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
