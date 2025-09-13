from rich.table import Table
import re
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
from portfolio_exporter.scripts import micro_momo_dashboard as _dash
import os, webbrowser
from portfolio_exporter.scripts import micro_momo_analyzer

# custom input handler: support multi-line commands and respect main or builtins input monkeypatches
import builtins
from types import SimpleNamespace
import os

_input_buffer: list[str] = []

# cache last symbol / expiry used by quick-chain prompts
last_symbol = SimpleNamespace(value="")
last_symbol.get = lambda ls=last_symbol: ls.value
last_expiry = SimpleNamespace(value="")
last_expiry.get = lambda le=last_expiry: le.value


def _input(prompt: str = "") -> str:
    """Simple input that keeps keystrokes visible in menu flows."""
    global _input_buffer
    if _input_buffer:
        return _input_buffer.pop(0)
    try:
        raw = builtins.input(prompt)
    except StopIteration:
        # Test harness exhausted: return to previous menu
        return "r"
    if "\r" in raw or "\n" in raw:
        lines = [line for line in raw.replace("\r", "\n").split("\n") if line]
        _input_buffer.extend(lines[1:])
        return lines[0]
    return raw


def _ask_symbol(prompt: str = "Symbol: ") -> str:
    """Prompt for a symbol, reusing last entry on blank input."""
    sym = _input(prompt).strip().upper() or last_symbol.get()
    if sym:
        last_symbol.value = sym
    return sym


def _ask_expiry(prompt: str = "Expiry (YYYY-MM-DD): ") -> str:
    """Prompt for an expiry (supports natural-language entries), reusing last entry on blank input."""
    exp = _input(prompt).strip() or last_expiry.get()
    if exp:
        last_expiry.value = exp
    return exp


def launch(status: StatusBar, default_fmt: str):
    current_fmt = default_fmt
    console = status.console if status else Console()

    def _external_scan(fmt: str) -> None:
        raw = _input("\u27b7  Enter tickers comma-separated: ")
        tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
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
            ("q", "Quick chain"),
            ("o", "Option chain snapshot"),
            ("n", "Net-Liq history"),
            ("m", "Micro-MOMO Analyzer"),
            ("d", "Micro-MOMO Dashboard"),
            ("x", "External technical scan"),
            ("y", "Pre-flight check (env & CSVs)"),
            ("z", "Run overnight batch"),
            ("f", f"Toggle output format (current: {current_fmt})"),
            ("r", "Return"),
        ]
        tbl = Table(title="Pre-Market")
        for key, label in menu_items:
            tbl.add_row(key, label)
        console.print(tbl)
        raw = _input("\u203a ").strip().lower()
        # Allow test harness to exit with '0' like the main menu
        if raw == "0":
            return
        # Allow multiple entries separated by spaces or commas
        tokens = [t for t in re.split(r"[\s,]+", raw) if t]
        for choice in tokens:
            if choice == "r":
                return
            if choice == "f":
                order = ["csv", "excel", "pdf"]
                idx = order.index(current_fmt)
                current_fmt = order[(idx + 1) % len(order)]
                continue

        # map choices to actions
        def _quick_chain(fmt: str = "") -> None:
            from portfolio_exporter.scripts import quick_chain

            quick_chain.run(last_symbol.get(), last_expiry.get())

        action_map = {
            "s": update_tickers.run,
            "h": historic_prices.run,
            "p": daily_pulse.run,
            "q": _quick_chain,
            "o": option_chain_snapshot.run,
            "n": net_liq_history_export.run,
            "m": lambda fmt=default_fmt: _run_micro_momo(console),
            "d": lambda fmt=default_fmt: launch_micro_momo_dashboard(status, fmt),
            "x": lambda fmt=default_fmt: _external_scan(fmt),
            "y": lambda fmt=default_fmt: orchestrate_dataset.preflight_check(
                no_pretty=bool(os.getenv("PE_QUIET"))
            ),
            "z": orchestrate_dataset.run,
        }
        action = action_map.get(choice)
        if action:
            label = dict(menu_items).get(choice, choice)
            if status:
                status.update(f"Running {label} …", "cyan")
            try:
                action(fmt=current_fmt)
            except Exception as exc:
                console.print(f"[red]Error running {label}:[/] {exc}")
            finally:
                if status:
                    status.update("Ready", "green")


def _run_micro_momo(console: Console) -> None:
    try:
        pe_test = os.getenv("PE_TEST_MODE")
        # Auto-config
        cfg = os.getenv("MOMO_CFG") or (
            "micro_momo_config.json"
            if os.path.exists("micro_momo_config.json")
            else ("tests/data/micro_momo_config.json" if pe_test else "micro_momo_config.json")
        )
        # Auto-input discovery
        if os.getenv("MOMO_INPUT"):
            inp = os.getenv("MOMO_INPUT")
        else:
            search_dirs = [
                os.getenv("MOMO_INPUT_DIR"),
                ".",
                "./data",
                "./scans",
                "./inputs",
                "tests/data" if pe_test else None,
            ]
            patterns = tuple((os.getenv("MOMO_INPUT_GLOB") or "meme_scan_*.csv").split(","))
            auto = find_latest_file([d for d in search_dirs if d], patterns)
            if pe_test and not auto:
                auto = "tests/data/meme_scan_sample.csv"
            inp = auto or "meme_scan.csv"
        out_dir = os.getenv("MOMO_OUT") or "out"
        argv = ["--input", inp, "--cfg", cfg, "--out_dir", out_dir]
        # Auto chains dir (optional)
        chd = os.getenv("MOMO_CHAINS_DIR") or auto_chains_dir(
            ["./option_chains", "./chains", "./data/chains", "tests/data" if pe_test else None]
        )
        if chd:
            argv += ["--chains_dir", chd]
        if pe_test:
            argv += ["--json", "--no-files"]
        micro_momo_analyzer.main(argv)
        console.print(f"[green]Micro-MOMO complete → {out_dir}[/]")
    except Exception as exc:  # pragma: no cover - menu path
        console.print(f"[red]Micro-MOMO error:[/] {exc}")


def launch_micro_momo_dashboard(status: StatusBar, fmt: str) -> None:  # noqa: ARG001
    try:
        # Use default output directory without prompting (consistent with other outputs)
        out_dir = os.getenv("MOMO_OUT") or "out"
        if status:
            status.update("Generating Micro-MOMO Dashboard", "cyan")
        _dash.main(["--out_dir", out_dir])
        path = os.path.join(out_dir, "micro_momo_dashboard.html")
        if os.path.exists(path):
            try:
                webbrowser.open(f"file://{os.path.abspath(path)}", new=2)
            except Exception:
                pass
            from rich.console import Console as _C

            _C().print(f"[green]Dashboard ready:[/] {path}")
        else:
            from rich.console import Console as _C

            _C().print(f"[yellow]Dashboard not found at:[/] {path}")
        if status:
            status.update("Ready", "green")
    except Exception as exc:  # pragma: no cover - UI path
        from rich.console import Console as _C

        _C().print(f"[red]Micro-MOMO Dashboard failed:[/] {exc}")
