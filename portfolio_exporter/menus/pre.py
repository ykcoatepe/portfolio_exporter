# custom input handler: support multi-line commands and respect main or builtins input monkeypatches
import builtins
import glob
import os
import re
import shutil
import time
import webbrowser
from types import SimpleNamespace

from rich.console import Console
from rich.table import Table

from portfolio_exporter.core import ui as core_ui
from portfolio_exporter.core.fs_utils import auto_chains_dir, find_latest_file
from portfolio_exporter.core.market_clock import pretty_tr, rth_window_tr
from portfolio_exporter.core.memory import get_pref, set_pref
from portfolio_exporter.core.proc import (
    start as sentinel_start,
)
from portfolio_exporter.core.proc import (
    start_module_logged,
    status_module,
    stop_module,
)
from portfolio_exporter.core.proc import (
    status as sentinel_status,
)
from portfolio_exporter.core.proc import (
    stop as sentinel_stop,
)
from portfolio_exporter.core.publish import (
    open_dashboard,
    open_in_finder,
    publish_pack,
)
from portfolio_exporter.core.symbols import load_alias_map, normalize_symbols
from portfolio_exporter.core.ui import StatusBar
from portfolio_exporter.scripts import (
    daily_pulse,
    historic_prices,
    micro_momo_analyzer,
    net_liq_history_export,
    option_chain_snapshot,
    orchestrate_dataset,
    tech_scan,
    update_tickers,
)
from portfolio_exporter.scripts import micro_momo_dashboard as _dash

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


def _normalize_session(session: str | None) -> str:
    if not session:
        return "auto"
    value = str(session).strip().lower()
    return value if value in {"auto", "rth", "premarket"} else "auto"


def _pref_to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _load_session_pref() -> str:
    env_session = os.getenv("MOMO_SESSION")
    if env_session:
        return _normalize_session(env_session)
    try:
        mem_session = get_pref("micro_momo.session")
    except Exception:
        mem_session = None
    if mem_session:
        return _normalize_session(mem_session)
    return "auto"


def _load_force_live_pref() -> bool:
    env_force = os.getenv("MOMO_FORCE_LIVE")
    if env_force is not None:
        return _pref_to_bool(env_force, False)
    try:
        mem_force = get_pref("micro_momo.force_live_default")
    except Exception:
        mem_force = None
    return _pref_to_bool(mem_force, False)


def _persist_session_pref(session: str) -> None:
    try:
        set_pref("micro_momo.session", _normalize_session(session))
    except Exception:
        pass


def _persist_force_live_pref(force_live: bool) -> None:
    try:
        set_pref("micro_momo.force_live_default", bool(force_live))
    except Exception:
        pass


def launch(status: StatusBar, default_fmt: str):
    current_fmt = default_fmt
    console = status.console if status else Console()

    def _external_scan(fmt: str) -> None:
        raw = _input("\u27b7  Enter tickers comma-separated: ")
        tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
        if status:
            status.update(f"Tech scan: {','.join(tickers)} …", "cyan")

        tech_scan.run(tickers=tickers, fmt=fmt)
        if status:
            status.update("Ready", "green")

    def _run_micro_momo_diag(
        local_console: Console,
        session_mode: str | None = None,
        force_live: bool | None = None,
        out_dir: str | None = None,
    ) -> None:
        target_out_dir = out_dir or os.getenv("MOMO_OUT") or "out"
        session_arg = _normalize_session(session_mode) if session_mode else _load_session_pref()
        force_flag = force_live if force_live is not None else _load_force_live_pref()
        try:
            from portfolio_exporter.scripts import micro_momo_diag as _diag

            diag_args = ["--out_dir", target_out_dir, "--session", session_arg]
            if force_flag:
                diag_args.append("--force-live")
            _diag.main(diag_args)
        except Exception as exc:
            local_console.print(f"[yellow]Diagnostics failed:[/] {exc}")

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
            "y": lambda fmt=default_fmt: _run_micro_momo_diag(console),
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
    symbols: str = ""

    def _yahoo_cache_dir(out_dir: str) -> str:
        return os.path.join(out_dir, ".cache")

    def _clear_yahoo_cache(out_dir: str, console) -> None:
        cache_dir = _yahoo_cache_dir(out_dir)
        hits = glob.glob(os.path.join(cache_dir, "yahoo_*"))
        if not hits:
            console.print("[yellow]No provider cache to clear.[/]")
            return
        cleared = 0
        for p in hits:
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
                cleared += 1
            except Exception:
                pass
        console.print(f"[green]Cleared {cleared} cache item(s).[/]")

    def _tail_file(path: str, n: int = 20) -> list[str]:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            return lines[-n:]
        except Exception:
            return []

    def _resolve_symbols_for_bg() -> str:
        env_syms = os.getenv("MOMO_SYMBOLS") or ""
        mem_syms = get_pref("micro_momo.symbols", "") or ""
        return (env_syms or mem_syms or symbols).strip()

    def _clear_saved_symbols(console) -> None:
        nonlocal symbols
        ans = core_ui.prompt_input(
            "Clear saved scanner symbols? Type 'CLEAR' to confirm, or press Enter to cancel: "
        ).strip()
        if ans != "CLEAR":
            console.print("[yellow]Canceled.[/]")
            return
        try:
            set_pref("micro_momo.symbols", "")
            symbols = ""
            console.print("[green]Saved symbols cleared.[/]")
        except Exception as exc:  # pragma: no cover - UI path
            from rich.console import Console as _C

            _C().print(f"[red]Failed to clear symbols:[/] {exc}")

    session_mode = _load_session_pref()
    force_live_default = _load_force_live_pref()

    def _session_label() -> str:
        return {"auto": "Auto", "rth": "RTH", "premarket": "Pre-market"}.get(session_mode, "Auto")

    def _set_session(new_session: str) -> None:
        nonlocal session_mode
        normalized = _normalize_session(new_session)
        if normalized == session_mode:
            console.print(f"[dim]Session guard unchanged ({_session_label()}).[/]")
            return
        session_mode = normalized
        _persist_session_pref(session_mode)
        console.print(f"[green]Session guard set to {_session_label()}[/]")

    def _toggle_force_live() -> None:
        nonlocal force_live_default
        force_live_default = not force_live_default
        _persist_force_live_pref(force_live_default)
        console.print(f"[green]Force-live default set to {'ON' if force_live_default else 'OFF'}[/]")

    def _session_args() -> list[str]:
        return ["--session", session_mode]

    try:
        pe_test = os.getenv("PE_TEST_MODE")
        while True:
            cfg_env = os.getenv("MOMO_CFG")
            cfg_candidates = [
                cfg_env,
                "micro_momo_config.json",
                "configs/micro_momo_config.json",
                ("tests/data/micro_momo_config.json" if pe_test else None),
            ]
            cfg = next((p for p in cfg_candidates if p and os.path.exists(p)), None)

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
                inp = auto

            out_dir = os.getenv("MOMO_OUT") or "out"
            argv_base: list[str] = ["--out_dir", out_dir]
            if inp:
                argv_base = ["--input", inp] + argv_base
            if cfg:
                argv_base += ["--cfg", cfg]
            chains_dir = os.getenv("MOMO_CHAINS_DIR") or auto_chains_dir(
                ["./option_chains", "./chains", "./data/chains", "tests/data" if pe_test else None]
            )
            if chains_dir:
                argv_base += ["--chains_dir", chains_dir]

            if inp and not os.path.exists(inp):
                console.print(f"[yellow]Scan CSV not found:[/] {inp}")
                console.print("[yellow]Enter symbols or provide a valid scan CSV before running.[/]")
                inp = None
                argv_base = ["--out_dir", out_dir]
                if cfg:
                    argv_base += ["--cfg", cfg]
                if chains_dir:
                    argv_base += ["--chains_dir", chains_dir]

            session_display = _session_label()
            force_display = "ON" if force_live_default else "OFF"
            console.print(
                "Options: [Enter] Run  ·  [B] Run in background  ·  [L] Run LIVE (background)  ·  [D] Diagnostics  ·  [S] Status  ·  [T] Stop background  ·  [R] Rebuild dashboard  ·  [K] Clear cache  ·  [J] Session guard (current: "
                f"{session_display})  ·  [F] Toggle force-live default (now: {force_display})  ·  [O] Open dashboard  ·  [C] Clear saved symbols  ·  [0] Back",
                highlight=False,
            )
            choice = core_ui.prompt_input("› ").strip().lower()

            if choice == "0":
                return
            if choice == "c":
                _clear_saved_symbols(console)
                continue
            if choice == "j":
                console.print("Session guard: [1] Auto  ·  [2] RTH only  ·  [3] Pre-market", highlight=False)
                sel = core_ui.prompt_input("Session › ").strip().lower()
                mapping = {
                    "1": "auto",
                    "auto": "auto",
                    "2": "rth",
                    "r": "rth",
                    "rth": "rth",
                    "3": "premarket",
                    "p": "premarket",
                    "pre": "premarket",
                    "pm": "premarket",
                    "premarket": "premarket",
                }
                if sel in mapping:
                    _set_session(mapping[sel])
                else:
                    console.print("[yellow]Session guard unchanged.[/]")
                continue
            if choice == "f":
                _toggle_force_live()
                continue
            if choice == "d":
                _run_micro_momo_diag(  # noqa: F821
                    console, session_mode, force_live_default, out_dir
                )
                continue
            if choice == "k":
                _clear_yahoo_cache(out_dir, console)
                continue
            if choice == "r":
                try:
                    _dash.main(["--out_dir", out_dir])
                    open_dashboard(out_dir)
                except Exception as exc:
                    console.print(f"[yellow]Dashboard rebuild failed:[/] {exc}")
                continue
            if choice == "s":
                st = status_module("momo_analyzer")
                running = st.get("running", False)
                console.print(
                    f"Analyzer: {'[green]RUNNING[/]' if running else '[red]STOPPED[/]'}   PID: {st.get('pid', '-')}"
                )
                try:
                    from pathlib import Path as _P

                    p = _P(out_dir) / "micro_momo_scored.csv"
                    if p.exists():
                        console.print(
                            f"Last scored mtime: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p.stat().st_mtime))}"
                        )
                except Exception:
                    pass
                log_path = (
                    st.get("log")
                    if isinstance(st.get("log"), str)
                    else os.path.join(out_dir, ".logs", "momo_analyzer.log")
                )
                lines = _tail_file(str(log_path), 20)
                if lines:
                    from rich.panel import Panel

                    console.print(
                        Panel.fit("".join(lines) or "(log empty)", title="log tail", border_style="cyan")
                    )
                else:
                    console.print("[dim]No log yet[/]")
                continue
            if choice == "t":
                res = stop_module("momo_analyzer")
                console.print(
                    f"[green]{res.get('msg', 'stopped')}[/]" if res.get("ok") else f"[yellow]{res.get('msg')}"
                )
                continue
            if choice == "o":
                open_dashboard(out_dir)
                continue
            if choice in {"b", "l"}:
                resolved = _resolve_symbols_for_bg()
                if not resolved:
                    console.print(
                        "[yellow]No symbols found.[/] Enter symbols first (press Enter), or provide a scan CSV."
                    )
                    continue
                bg_args = ["--out_dir", out_dir, "--symbols", resolved] + _session_args()
                if cfg and os.path.exists(cfg):
                    bg_args += ["--cfg", cfg]
                if chains_dir:
                    bg_args += ["--chains_dir", chains_dir]
                if choice == "l" or force_live_default:
                    bg_args.append("--force-live")
                log_path = os.path.join(out_dir, ".logs", "momo_analyzer.log")
                res = start_module_logged(
                    "momo_analyzer",
                    "portfolio_exporter.scripts.micro_momo_analyzer",
                    bg_args,
                    log_path,
                )
                label = "Analyzer (LIVE)" if choice == "l" else "Analyzer"
                console.print(
                    f"[green]{label} started[/] PID {res.get('pid')}  log: {res.get('log')}"
                    if res.get("ok")
                    else f"[yellow]{res.get('msg')}"
                )
                return

            try:
                d_syms = os.getenv("MOMO_SYMBOLS") or (get_pref("micro_momo.symbols") or "")
                sym_in = _input(f"Symbols (comma, optional) [{d_syms}]: ").strip() or d_syms
            except Exception:
                sym_in = os.getenv("MOMO_SYMBOLS") or (get_pref("micro_momo.symbols") or "")
            run_args = list(argv_base)
            if sym_in:
                alias_map = load_alias_map([os.getenv("MOMO_ALIASES_PATH") or ""])
                syms = normalize_symbols([s for s in sym_in.split(",") if s.strip()], alias_map)
                if syms:
                    symbols = ",".join(syms)
                    run_args += ["--symbols", symbols]
                    try:
                        set_pref("micro_momo.symbols", sym_in)
                    except Exception:
                        pass
            if not sym_in and not inp:
                console.print(
                    "[yellow]No symbols provided and no scan CSV available; cannot run analyzer.[/]"
                )
                continue
            run_args += _session_args()
            if force_live_default:
                run_args.append("--force-live")
            dm = os.getenv("MOMO_DATA_MODE")
            if dm:
                run_args += ["--data-mode", dm]
            prv = os.getenv("MOMO_PROVIDERS")
            if prv:
                run_args += ["--providers", prv]
            off = os.getenv("MOMO_OFFLINE")
            if off and off.lower() not in ("0", "false"):
                run_args.append("--offline")
            if pe_test:
                run_args += ["--json", "--no-files"]
            micro_momo_analyzer.main(run_args)
            console.print(f"[green]Micro-MOMO complete → {out_dir}[/]")
            return
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

        # Read menu toggles from memory (defaults: ON/10)
        try:
            allow_aft = (get_pref("sentinel.allow_afternoon_rearm") or "true").lower() not in (
                "0",
                "false",
                "no",
            )
        except Exception:
            allow_aft = True
        try:
            allow_halt = (get_pref("sentinel.halt_rearm") or "true").lower() not in ("0", "false", "no")
        except Exception:
            allow_halt = True
        try:
            require_recross = (get_pref("sentinel.require_vwap_recross") or "true").lower() not in (
                "0",
                "false",
                "no",
            )
        except Exception:
            require_recross = True
        try:
            cd_raw = get_pref("sentinel.cooldown_bars") or "10"
            cooldown_bars = int(cd_raw)
        except Exception:
            cooldown_bars = 10
        # Small UX note for operators
        console.print(
            f"[dim]Recross[/]: {'ON' if require_recross else 'OFF'}  [dim]Cooldown bars[/]: {cooldown_bars}",
            highlight=False,
        )
        # Show halt re-arm parameters
        try:
            halt_on = (get_pref("sentinel.halt_rearm") or "true").lower() not in ("0", "false", "no")
        except Exception:
            halt_on = True
        try:
            mini_orb = int(get_pref("sentinel.halt_mini_orb_minutes") or 3)
        except Exception:
            mini_orb = 3
        try:
            grace = int(get_pref("sentinel.halt_rearm_grace_sec") or 45)
        except Exception:
            grace = 45
        try:
            max_per_day = int(get_pref("sentinel.max_halts_per_day") or 1)
        except Exception:
            max_per_day = 1
        console.print(
            f"[dim]Halt re-arm[/]: {'ON' if halt_on else 'OFF'}  •  [dim]mini-ORB[/]: {mini_orb}m  •  [dim]grace[/]: {grace}s  •  [dim]max/day[/]: {max_per_day}",
            highlight=False,
        )
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
            f"[b]5[/]) Toggle 1 post-halt re-arm (currently: {'ON' if allow_halt else 'OFF'})\n"
            f"        [b]6[/]) Toggle 'Require VWAP recross' (currently: {'ON' if require_recross else 'OFF'})  "
            f"[b]7[/]) Set cooldown bars (current: {cooldown_bars})  "
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
                f"[green]Started[/] PID {res.get('pid')}" if res.get("ok") else f"[yellow]{res.get('msg')}"
            )
        elif choice == "2":
            res = sentinel_stop()
            console.print(
                f"[green]{res.get('msg', 'stopped')}[/]" if res.get("ok") else f"[yellow]{res.get('msg')}"
            )
        elif choice == "3":
            _show_active_positions(console)
        elif choice == "4":
            try:
                set_pref("sentinel.allow_afternoon_rearm", not allow_aft)
                console.print(f"[green]Afternoon re-arm set to[/] {'ON' if not allow_aft else 'OFF'}")
            except Exception as exc:
                console.print(f"[yellow]Failed to update preference:[/] {exc}")
        elif choice == "5":
            try:
                set_pref("sentinel.halt_rearm", not allow_halt)
                console.print(f"[green]Post-halt re-arm set to[/] {'ON' if not allow_halt else 'OFF'}")
            except Exception as exc:
                console.print(f"[yellow]Failed to update preference:[/] {exc}")
        elif choice == "6":
            try:
                set_pref("sentinel.require_vwap_recross", not require_recross)
                console.print(
                    f"[green]Require VWAP recross set to[/] {'ON' if not require_recross else 'OFF'}"
                )
            except Exception as exc:
                console.print(f"[yellow]Failed to update preference:[/] {exc}")
        elif choice == "7":
            try:
                val = core_ui.prompt_input("Cooldown bars (integer, e.g., 10): ").strip()
                new_cd = max(0, int(val))
                set_pref("sentinel.cooldown_bars", new_cd)
                console.print(f"[green]Cooldown bars set to[/] {new_cd}")
            except Exception:
                console.print("[yellow]Invalid number[/]")
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
