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
    actions = {
        "q": ("Snapshot quotes", live_feed.run),
        "t": ("Tech signals", tech_signals_ibkr.run),
        "g": ("Portfolio Greeks", portfolio_greeks.run),
        "r": ("Risk dashboard", risk_watch.run),
        "c": ("Theta / Gamma caps", lambda: (theta_cap.run(), gamma_scalp.run())),
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
