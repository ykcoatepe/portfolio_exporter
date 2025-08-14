from rich.console import Console
from rich.table import Table
from portfolio_exporter.scripts import (
    trades_report,
    order_builder,
    roll_manager,
    option_chain_snapshot,
    net_liq_history_export,
    daily_report,
)
import os

# Menu for trade-related utilities


def launch(status, default_fmt):
    console = status.console if status else Console()
    while True:
        entries = [
            ("e", "Executions / open orders"),
            ("b", "Build order"),
            ("l", "Roll positions"),
            ("q", "Quick option chain"),
            ("n", "Net-Liq (CLI)"),
            ("d", "Daily report (HTML/PDF)"),
            ("r", "Return"),
        ]
        tbl = Table(title="Trades & Reports")
        for k, lbl in entries:
            tbl.add_row(k, lbl)
        console.print(tbl)
        raw = input("› ").strip().lower()
        # Allow multiple entries separated by spaces or commas
        import re as _re
        tokens = [t for t in _re.split(r"[\s,]+", raw) if t]
        for ch in tokens:
            if ch == "r":
                return
            label_map = dict(entries)
            dispatch = {
                "e": lambda: trades_report.run(fmt=default_fmt, show_actions=True),
                "b": order_builder.run,
                "l": lambda: roll_manager.run(),
                "q": lambda: option_chain_snapshot.run(fmt=default_fmt),
                "n": lambda: net_liq_history_export.main(
                    ["--quiet", "--no-pretty"] if os.getenv("PE_QUIET") else []
                ),
                "d": lambda: daily_report.main(
                    ["--no-pretty"] if os.getenv("PE_QUIET") else []
                ),
            }.get(ch)
            if dispatch:
                label = label_map.get(ch, ch)
                if status:
                    status.update(f"Running {label} …", "cyan")
                try:
                    dispatch()
                except Exception as exc:
                    console.print(f"[red]Error running {label}:[/] {exc}")
                finally:
                    if status:
                        status.update("Ready", "green")
