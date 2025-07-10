from rich.table import Table
from portfolio_exporter.core.ui import StatusBar
from portfolio_exporter.scripts import (
    update_tickers,
    historic_prices,
    daily_pulse,
    option_chain_snapshot,
    net_liq_history_export,
    orchestrate_dataset,
)


def launch(status: StatusBar, default_fmt: str):
    while True:
        tbl = Table(title="Pre-Market")
        for key, label in [
            ("s", "Sync tickers"),
            ("h", "Historic prices"),
            ("p", "Daily pulse"),
            ("o", "Option chain snapshot"),
            ("n", "Net-Liq history"),
            ("z", "Run overnight batch"),
            ("r", "Return"),
        ]:
            tbl.add_row(key, label)
        status.console.print(tbl)
        choice = input("\u203a ").strip().lower()
        if choice == "r":
            break
        action = {
            "s": update_tickers.run,
            "h": historic_prices.run,
            "p": daily_pulse.run,
            "o": option_chain_snapshot.run,
            "n": net_liq_history_export.run,
            "z": orchestrate_dataset.run,
        }.get(choice)
        if action:
            status.update(f"Running {choice} …", "cyan")
            action(fmt=default_fmt)
            status.update("Ready", "green")
