from rich.table import Table
from portfolio_exporter.core.ui import StatusBar
from portfolio_exporter.scripts import (
    update_tickers,
    historic_prices,
    daily_pulse,
    option_chain_snapshot,
    net_liq_history_export,
    orchestrate_dataset,
    tech_scan,
)


def launch(status: StatusBar, default_fmt: str):
    current_fmt = default_fmt

    def _external_scan(fmt: str) -> None:
        tickers = input("\u27b7  Enter tickers comma-separated: ").upper().split(",")
        status.update(f"Tech scan: {','.join(tickers)} …", "cyan")
        from portfolio_exporter.scripts import tech_scan

        tech_scan.run(tickers=tickers, fmt=fmt)
        status.update("Ready", "green")

    while True:
        tbl = Table(title="Pre-Market")
        for key, label in [
            ("s", "Sync tickers"),
            ("h", "Historic prices"),
            ("p", "Daily pulse"),
            ("o", "Option chain snapshot"),
            ("n", "Net-Liq history"),
            ("x", "External technical scan"),
            ("z", "Run overnight batch"),
            ("f", f"Toggle output format (current: {current_fmt})"),
            ("r", "Return"),
        ]:
            tbl.add_row(key, label)
        status.console.print(tbl)
        choice = input("\u203a ").strip().lower()
        if choice == "r":
            break
        if choice == "f":
            order = ["csv", "excel", "pdf"]
            idx = order.index(current_fmt)
            current_fmt = order[(idx + 1) % len(order)]
            continue
        action = {
            "s": update_tickers.run,
            "h": historic_prices.run,
            "p": daily_pulse.run,
            "o": option_chain_snapshot.run,
            "n": net_liq_history_export.run,
            "x": lambda fmt=default_fmt: _external_scan(fmt),
            "z": orchestrate_dataset.run,
        }.get(choice)
        if action:
            status.update(f"Running {choice} …", "cyan")
            action(fmt=current_fmt)
            status.update("Ready", "green")
