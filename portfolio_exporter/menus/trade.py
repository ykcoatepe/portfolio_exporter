from rich.table import Table
from portfolio_exporter.scripts import (
    trades_report,
    order_builder,
    roll_manager,
    option_chain_snapshot,
)


def launch(status, default_fmt):
    while True:
        tbl = Table(title="Trades & Reports")
        for k, lbl in [
            ("e", "Executions / open orders"),
            ("b", "Build order (stub)"),
            ("l", "Roll positions (stub)"),
            ("q", "Quick option chain"),
            ("r", "Return"),
        ]:
            tbl.add_row(k, lbl)
        status.console.print(tbl)
        ch = input("› ").strip().lower()
        if ch == "r":
            break
        dispatch = {
            "e": lambda: trades_report.run(fmt=default_fmt),
            "b": order_builder.run,
            "l": roll_manager.run,
            "q": lambda: option_chain_snapshot.run(fmt=default_fmt),
        }.get(ch)
        if dispatch:
            status.update(f"Running {lbl} …", "cyan")
            dispatch()
            status.update("Ready", "green")
