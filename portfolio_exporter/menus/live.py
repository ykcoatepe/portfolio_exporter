from rich.table import Table
from rich.console import Console
from portfolio_exporter.scripts import (
    live_feed,
    tech_signals_ibkr,
    portfolio_greeks,
)
from portfolio_exporter.core import risk_dash
from portfolio_exporter.core import caps_dash


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

    actions = {
        "q": ("Snapshot quotes", _snapshot),
        "t": ("Tech signals", tech_signals_ibkr.run),
        "g": ("Portfolio Greeks", portfolio_greeks.run),
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
