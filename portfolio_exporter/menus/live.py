from rich.table import Table
import re
from rich.console import Console
import builtins as _builtins
import pandas as pd
from portfolio_exporter.scripts import (
    live_feed,
    tech_signals_ibkr,
    portfolio_greeks,
)
from portfolio_exporter.core import risk_dash
from portfolio_exporter.core import caps_dash
from portfolio_exporter.core.io import latest_file


def _user_tech_signals(status, default_fmt):
    tickers = input("\u27b7  Enter tickers (comma-sep): ").upper().split(",")
    from portfolio_exporter.scripts import tech_signals_ibkr

    if status:
        status.update("Tech signals running …", "cyan")
    tech_signals_ibkr.run(tickers=tickers, fmt=default_fmt)
    if status:
        status.update("Ready", "green")


def launch(status, default_fmt):
    console = status.console if status else Console()

    def _snapshot():
        try:
            live_feed.run(fmt=default_fmt, include_indices=True)
        except TypeError:
            # backward compatibility for patched or legacy signatures
            live_feed.run()

    def _run_greeks():
        portfolio_greeks.run(fmt=default_fmt)
        pos_path = latest_file("portfolio_greeks_positions", default_fmt)
        combos_path = latest_file("portfolio_greeks_combos", default_fmt)
        if pos_path and combos_path:
            pos_df = pd.read_csv(pos_path)
            combos_df = pd.read_csv(combos_path)
            console.print(
                f"[green]Positions: {len(pos_df)} legs / {len(combos_df)} combos"
            )

    actions = {
        "q": ("Snapshot quotes", _snapshot),
        "t": ("Tech signals", tech_signals_ibkr.run),
        "g": ("Portfolio Greeks", _run_greeks),
        "r": ("Risk dashboard", lambda: risk_dash.run()),
        "c": ("Theta / Gamma Caps", lambda: caps_dash.run()),
        "u": (
            "User-defined Tech Signals",
            lambda: _user_tech_signals(status, default_fmt),
        ),
    }

    while True:
        tbl = Table(title="Live-Market")
        for key, (label, _) in list(actions.items()) + [("b", ("Back", None))]:
            tbl.add_row(key, label)
        console.print(tbl)
        try:
            raw = __import__("main").input("\u203a ")
        except Exception:
            raw = _builtins.input("\u203a ")
        raw = raw.strip().lower()
        # Allow multiple entries separated by spaces or commas
        tokens = [t for t in re.split(r"[\s,]+", raw) if t]
        for ch in tokens:
            if ch == "b":
                return
            entry = actions.get(ch)
            if entry:
                label, func = entry
                if status:
                    status.update(f"Running {label} …", "cyan")
                try:
                    func()
                except Exception as exc:
                    console.print(f"[red]Error running {label}:[/] {exc}")
                finally:
                    if status:
                        status.update("Ready", "green")
