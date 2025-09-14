from rich.table import Table
import re
from rich.console import Console
from portfolio_exporter.core.ui import StatusBar
from portfolio_exporter.core.publish import (
    publish_pack,
    open_in_finder,
    open_dashboard,
)
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
from portfolio_exporter.core.memory import get_pref, set_pref
from portfolio_exporter.core import ui as core_ui
from portfolio_exporter.core.proc import (
    start as sentinel_start,
    stop as sentinel_stop,
    status as sentinel_status,
)
from portfolio_exporter.core.fs_utils import find_latest_file, auto_chains_dir
from portfolio_exporter.core.symbols import load_alias_map, normalize_symbols
from portfolio_exporter.core.market_clock import rth_window_tr, pretty_tr

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
            ("g", "Open Published Folder (today)"),
            ("u", "Sentinel (Start/Stop/Status)"),
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
            "g": lambda fmt=default_fmt: launch_open_published(status, fmt),
            "u": lambda fmt=default_fmt: launch_sentinel_menu(status, fmt),
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
        cfg_env = os.getenv("MOMO_CFG")
        cfg_candidates = [
            cfg_env,
            "micro_momo_config.json",
            "configs/micro_momo_config.json",
            ("tests/data/micro_momo_config.json" if pe_test else None),
        ]
        cfg = next((p for p in cfg_candidates if p and os.path.exists(p)), None)
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
        argv = ["--input", inp, "--out_dir", out_dir]
        if cfg:
            argv += ["--cfg", cfg]
        # Auto chains dir (optional)
        chd = os.getenv("MOMO_CHAINS_DIR") or auto_chains_dir(
            ["./option_chains", "./chains", "./data/chains", "tests/data" if pe_test else None]
        )
        if chd:
            argv += ["--chains_dir", chd]
        # Optional symbols override (comma-separated). Blank → keep file-based defaults.
        # Prefill from env or memory; persist back to memory on use.
        try:
            d_syms = os.getenv("MOMO_SYMBOLS") or (get_pref("micro_momo.symbols") or "")
            # Use menu-aware input to keep keystrokes visible in this UI
            sym_in = _input(f"Symbols (comma, optional) [{d_syms}]: ").strip() or d_syms
        except Exception:
            sym_in = os.getenv("MOMO_SYMBOLS") or (get_pref("micro_momo.symbols") or "")
        if sym_in:
            # Normalize against alias map before passing down to analyzer
            alias_map = load_alias_map([os.getenv("MOMO_ALIASES_PATH") or ""])  # env path wins, if set
            syms = normalize_symbols(sym_in.split(","), alias_map)
            argv += ["--symbols", ",".join(syms)]
            try:
                set_pref("micro_momo.symbols", sym_in)
            except Exception:
                pass
        # Optional data-mode/providers/offline via env passthrough
        dm = os.getenv("MOMO_DATA_MODE")
        if dm:
            argv += ["--data-mode", dm]
        prv = os.getenv("MOMO_PROVIDERS")
        if prv:
            argv += ["--providers", prv]
        off = os.getenv("MOMO_OFFLINE")
        if off and off not in ("0", "false", "False"):
            argv += ["--offline"]
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


def launch_open_published(status: StatusBar, fmt: str) -> None:  # noqa: ARG001
    try:
        if status:
            status.update("Publishing/Opening", "cyan")
        out_dir = os.getenv("MOMO_OUT") or "out"
        pub = publish_pack(out_dir)  # no-op if already copied today
        # On macOS, `open` will open the folder or file in the default app
        open_in_finder(pub)
        # and try to open the dashboard too, if present
        open_dashboard(pub)
        if status:
            status.update("Ready", "green")
    except Exception as exc:  # pragma: no cover - UI path
        from rich.console import Console

        Console().print(f"[red]Open Published Folder failed:[/] {exc}")


def launch_sentinel_menu(status, fmt):  # noqa: ARG001 - fmt reserved for future
    from rich.console import Console

    console = status.console if status else Console()
    while True:
        s = sentinel_status()
        running = bool(s.get("running"))
        console.rule("[bold]Sentinel")
        # Display today's TR-local schedule derived from US RTH
        try:
            sched = rth_window_tr()
            console.print(
                f"[dim]TR schedule[/]: open {pretty_tr(sched.open_tr)}, "
                f"afternoon {pretty_tr(sched.afternoon_rearm_tr)}, "
                f"cutoff {pretty_tr(sched.no_new_signals_after_tr)}, "
                f"close {pretty_tr(sched.close_tr)}",
                highlight=False,
            )
        except Exception:
            pass

        # Read menu toggles from memory (defaults: ON)
        try:
            allow_aft = (get_pref("sentinel.allow_afternoon_rearm") or "true").lower() not in ("0", "false", "no")
        except Exception:
            allow_aft = True
        try:
            allow_halt = (get_pref("sentinel.halt_rearm") or "true").lower() not in ("0", "false", "no")
        except Exception:
            allow_halt = True
        console.print(
            f"Status: {'[green]RUNNING[/]' if running else '[red]STOPPED[/]'}",
            highlight=False,
        )
        if running:
            console.print(
                f"PID: {s.get('pid')}  Started: {s.get('started_at')}  Args: {s.get('argv')}",
                overflow="fold",
            )
        console.print(
            "\nOptions: [b]1[/]) Start  [b]2[/]) Stop  [b]3[/]) Active positions  "
            f"[b]4[/]) Toggle afternoon re-arm (currently: {'ON' if allow_aft else 'OFF'})  "
            f"[b]5[/]) Toggle 1 post-halt re-arm (currently: {'ON' if allow_halt else 'OFF'})  "
            "[b]0[/]) Back"
        )

        choice = core_ui.prompt_input("› ").strip()
        if choice == "0":
            return
        if choice == "1":
            momo_scored = os.getenv("MOMO_SCORED") or "out/micro_momo_scored.csv"
            cfg = os.getenv("MOMO_CFG") or "micro_momo_config.json"
            out_dir = os.getenv("MOMO_OUT") or "out"
            interval = os.getenv("MOMO_INTERVAL") or "10"
            args = [
                "--scored-csv",
                momo_scored,
                "--cfg",
                cfg,
                "--out_dir",
                out_dir,
                "--interval",
                interval,
            ]
            if os.getenv("MOMO_WEBHOOK"):
                args += ["--webhook", os.getenv("MOMO_WEBHOOK")]
            if os.getenv("MOMO_THREAD"):
                args += ["--thread", os.getenv("MOMO_THREAD")]
            if (os.getenv("MOMO_OFFLINE") or "").lower() in ("1", "true", "yes"):
                args += ["--offline"]
            res = sentinel_start(args)
            console.print(
                f"[green]Started[/] PID {res.get('pid')}"
                if res.get("ok")
                else f"[yellow]{res.get('msg')}"
            )
        elif choice == "2":
            res = sentinel_stop()
            console.print(
                f"[green]{res.get('msg', 'stopped')}[/]"
                if res.get("ok")
                else f"[yellow]{res.get('msg')}"
            )
        elif choice == "3":
            _show_active_positions(console)
        elif choice == "4":
            try:
                set_pref("sentinel.allow_afternoon_rearm", not allow_aft)
                console.print(
                    f"[green]Afternoon re-arm set to[/] {'ON' if not allow_aft else 'OFF'}"
                )
            except Exception as exc:
                console.print(f"[yellow]Failed to update preference:[/] {exc}")
        elif choice == "5":
            try:
                set_pref("sentinel.halt_rearm", not allow_halt)
                console.print(
                    f"[green]Post-halt re-arm set to[/] {'ON' if not allow_halt else 'OFF'}"
                )
            except Exception as exc:
                console.print(f"[yellow]Failed to update preference:[/] {exc}")
        else:
            console.print("[yellow]Unknown choice[/]")


def _show_active_positions(console):
    import csv

    p = "out/micro_momo_journal.csv"
    if not os.path.exists(p):
        console.print("[yellow]No journal found (out/micro_momo_journal.csv)[/]")
        return
    with open(p, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    active = [r for r in rows if (str(r.get("status", "")).lower() in ("pending", "triggered"))]
    if not active:
        console.print("[green]No active positions[/]")
        return
    from rich.table import Table

    t = Table(title="Active positions")
    for c in [
        "symbol",
        "status",
        "direction",
        "structure",
        "contracts",
        "entry_trigger",
    ]:
        t.add_column(c)
    for r in active:
        t.add_row(
            r.get("symbol", ""),
            r.get("status", ""),
            r.get("direction", ""),
            r.get("structure", ""),
            str(r.get("contracts", "")),
            (r.get("entry_trigger", "") or "")[:80],
        )
    console.print(t)
