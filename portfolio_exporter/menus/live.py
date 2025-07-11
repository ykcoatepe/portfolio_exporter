from rich.table import Table
from rich.console import Console
from portfolio_exporter.scripts import (
    live_feed,
    tech_signals_ibkr,
    portfolio_greeks,
    risk_watch,
    theta_cap,
    gamma_scalp,
)


def launch(status):
    console = status.console if status else Console()
    actions = {
        "q": ("Snapshot quotes", live_feed.run),
        "t": ("Tech signals", tech_signals_ibkr.run),
        "g": ("Portfolio Greeks", portfolio_greeks.run),
        "r": ("Risk dashboard", risk_watch.run),
        "c": ("Theta / Gamma caps", lambda: (theta_cap.run(), gamma_scalp.run())),
    }

    while True:
        tbl = Table(title="Live-Market")
        for key, (label, _) in list(actions.items()) + [("b", ("Back", None))]:
            tbl.add_row(key, label)
        console.print(tbl)
        ch = input("\u203a ").strip().lower()
        if ch == "b":
            break
        entry = actions.get(ch)
        if entry:
            label, func = entry
            if status:
                status.update(f"Running {label} …", "cyan")
            func()
            if status:
                status.update("Ready", "green")
