from rich.table import Table
from rich.console import Console
from portfolio_exporter.scripts import (
    trades_report,
    order_builder,
    roll_manager,
    option_chain_snapshot,
    net_liq_history_export,
)


def launch(status, default_fmt):
    console = status.console if status else Console()
    while True:
        tbl = Table(title="Trades & Reports")
        for k, lbl in [
            ("e", "Executions / open orders"),
            ("b", "Build order"),
            ("l", "Roll positions (stub)"),
            ("q", "Quick option chain"),
            ("v", "View Net-Liq chart"),
            ("r", "Return"),
        ]:
            tbl.add_row(k, lbl)
        console.print(tbl)
        ch = input("› ").strip().lower()
        if ch == "r":
            break
        dispatch = {
            "e": lambda: trades_report.run(fmt=default_fmt, show_actions=True),
            "b": order_builder.run,
            "l": roll_manager.run,
            "q": lambda: option_chain_snapshot.run(fmt=default_fmt),
            "v": lambda: net_liq_history_export.run(fmt=default_fmt, plot=True),
        }.get(ch)
        if dispatch:
            if status:
                status.update(f"Running {lbl} …", "cyan")
            dispatch()
            if status:
                status.update("Ready", "green")
