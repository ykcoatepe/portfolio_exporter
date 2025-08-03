from rich.table import Table
from rich.console import Console
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

# custom input handler: support multi-line commands and respect main or builtins input monkeypatches
import builtins

_input_buffer: list[str] = []

# cache last symbol / expiry used by quick-chain prompts
_last_used: dict[str, str] = {"symbol": "", "expiry": ""}


def _input(prompt: str = "") -> str:
    """Fetch one command from potentially multi-line input buffer."""
    global _input_buffer
    if _input_buffer:
        return _input_buffer.pop(0)
    try:
        # dynamic import to avoid circular dependency
        raw = __import__("main").input(prompt)
    except Exception:
        raw = builtins.input(prompt)
    if "\r" in raw or "\n" in raw:
        lines = [line for line in raw.replace("\r", "\n").split("\n") if line]
        _input_buffer.extend(lines[1:])
        return lines[0]
    return raw


def _ask_symbol(prompt: str = "Symbol: ") -> str:
    """Prompt for a symbol, reusing last entry on blank input."""
    sym = _input(prompt).strip().upper()
    if not sym:
        sym = _last_used.get("symbol", "")
    if sym:
        _last_used["symbol"] = sym
    return sym


def _ask_expiry(prompt: str = "Expiry (YYYY-MM-DD): ") -> str:
    """Prompt for an expiry, reusing last entry on blank input."""
    exp = _input(prompt).strip()
    if not exp:
        exp = _last_used.get("expiry", "")
    if exp:
        _last_used["expiry"] = exp
    return exp


def launch(status: StatusBar, default_fmt: str):
    current_fmt = default_fmt
    console = status.console if status else Console()

    def _external_scan(fmt: str) -> None:
        tickers = _input("\u27b7  Enter tickers comma-separated: ").upper().split(",")
        if status:
            status.update(f"Tech scan: {','.join(tickers)} …", "cyan")
        from portfolio_exporter.scripts import tech_scan

        tech_scan.run(tickers=tickers, fmt=fmt)
        if status:
            status.update("Ready", "green")

    while True:
        # build menu entries and display table
        menu_items = [
            ("s", "Sync tickers"),
            ("h", "Historic prices"),
            ("p", "Daily pulse"),
            ("o", "Option chain snapshot"),
            ("n", "Net-Liq history"),
            ("x", "External technical scan"),
            ("z", "Run overnight batch"),
            ("f", f"Toggle output format (current: {current_fmt})"),
            ("r", "Return"),
        ]
        tbl = Table(title="Pre-Market")
        for key, label in menu_items:
            tbl.add_row(key, label)
        console.print(tbl)
        choice = _input("\u203a ").strip().lower()
        if choice == "r":
            break
        if choice == "f":
            order = ["csv", "excel", "pdf"]
            idx = order.index(current_fmt)
            current_fmt = order[(idx + 1) % len(order)]
            continue
        # map choices to actions
        action_map = {
            "s": update_tickers.run,
            "h": historic_prices.run,
            "p": daily_pulse.run,
            "o": option_chain_snapshot.run,
            "n": net_liq_history_export.run,
            "x": lambda fmt=default_fmt: _external_scan(fmt),
            "z": orchestrate_dataset.run,
        }
        action = action_map.get(choice)
        if action:
            label = dict(menu_items).get(choice, choice)
            if status:
                status.update(f"Running {label} …", "cyan")
            action(fmt=current_fmt)
            if status:
                status.update("Ready", "green")
