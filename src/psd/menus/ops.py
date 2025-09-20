"""
PSD Ops Menu - start/stop/status for the live dashboard
=======================================================

What this is
------------
A small Rich TUI that orchestrates the three PSD processes:
  - ingestor  -> builds snapshots (positions/marks/greeks/risk)
  - scanner   -> evaluates rules; emits breach events
  - web       -> FastAPI app exposing /state, /stream (SSE), /healthz, /metrics

Menu
----
  [1] Status          Show which services are running and their PIDs
  [2] Stop PSD        Gracefully stop all tracked services (SIGINT->SIGTERM->SIGKILL)
  [3] Open Dashboard  Open http://127.0.0.1:<port> in the default browser
  [4] Start PSD       Start ingestor + scanner + web, persist PIDs, open dashboard
  [q] Quit            Exit the menu

Paths & files
-------------
  - Run dir:        ${PSD_RUN_DIR:-run}/
  - PID file:       run/psd-pids.json  ("ingestor":PID,"scanner":PID,"web":PID,"port":PORT)
  - Logs:           run/ingestor.log, run/scanner.log, run/web.log  (stdout/stderr redirected)

Config
------
  - PSD_PORT         Web port (default 51127)
  - PSD_RUN_DIR      Runtime dir for logs & PID file (default "run")
  - App-specific:    PSD_SNAPSHOT_FN / PSD_RULES_FN, IB_*... (read by the services)
  - IB_PORT          Default: TWS live port 7496 (paper/simulated uses 7497)

Idempotency & safety
--------------------
- Start is idempotent: if a PID is alive, that service isn't spawned again.
- Stop is careful: SIGINT -> wait 3s -> SIGTERM -> wait 3s -> SIGKILL (if available).
- PID file is kept in sync: removed when nothing remains, updated if something survives.

Troubleshooting
---------------
- "web" doesn't start: ensure `uvicorn` is on PATH (same venv as this menu).
- Dashboard doesn't update: check `run/*.log` and that PSD_SNAPSHOT_FN / PSD_RULES_FN are set.
- Port in use: set PSD_PORT to a free port before starting.
"""

from __future__ import annotations

import json
import os
import random
import signal
import subprocess
import sys
import time
import webbrowser
from collections.abc import Iterable, Mapping
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

RUN_DIR = Path(os.getenv("PSD_RUN_DIR", "run"))
PID_FILE = RUN_DIR / "psd-pids.json"
SERVICES = ("ingestor", "scanner", "web")
DEFAULT_PORT = 51127

_PROCESS_COMMANDS: Mapping[str, list[str]] = {
    "ingestor": [sys.executable, "-m", "psd.ingestor.main"],
    "scanner": [sys.executable, "-m", "psd.sentinel.scan"],
    "web": [
        "uvicorn",
        "--factory",
        "psd.web.server:make_app",
        "--host",
        "0.0.0.0",
        "--port",
        "{port}",
        "--ws",
        "none",
    ],
}
_LOG_NAMES = {
    "ingestor": "ingestor.log",
    "scanner": "scanner.log",
    "web": "web.log",
}

LOG_TAIL_LINES = int(os.getenv("PSD_LOG_TAIL_LINES", "40"))

ENV_SUMMARY_KEYS: tuple[str, ...] = (
    "PSD_SNAPSHOT_FN",
    "PSD_RULES_FN",
    "IB_HOST",
    "IB_PORT",
    "IB_CLIENT_ID",
)


def _load_env_file(path: str = ".env") -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    return env


def _with_defaults(base: Mapping[str, str]) -> dict[str, str]:
    out = dict(base)
    out.setdefault("PSD_SNAPSHOT_FN", "portfolio_exporter.psd_adapter:snapshot_once")
    out.setdefault("PSD_RULES_FN", "portfolio_exporter.psd_rules:evaluate")
    out.setdefault("IB_HOST", "127.0.0.1")
    out.setdefault("IB_PORT", "7496")
    if not out.get("IB_CLIENT_ID"):
        seed = 1000 + (os.getpid() % 7000) + random.randint(0, 999)
        out["IB_CLIENT_ID"] = str(seed)
    return out


def _port_from_env() -> int:
    raw = os.getenv("PSD_PORT", str(DEFAULT_PORT))
    try:
        return int(raw)
    except ValueError:  # fallback to safe default
        return DEFAULT_PORT


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def _wait_for_exit(pid: int, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return not _alive(pid)


def _load_pid_file(console: Console | None = None) -> dict[str, object]:
    try:
        content = PID_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        if console:
            console.print(f"[red]Failed to parse {PID_FILE}: {exc}[/red]")
        return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, object] = {}
    env_data: dict[str, str] | None = None
    for key, value in data.items():
        if key == "port":
            try:
                result[key] = int(value)
            except (TypeError, ValueError):
                continue
        elif key in SERVICES:
            try:
                result[key] = int(value)
            except (TypeError, ValueError):
                continue
        elif key == "env" and isinstance(value, dict):
            env_data = {str(k): str(v) for k, v in value.items() if isinstance(k, str)}
    if env_data:
        result["env"] = env_data
    return result


def _save_pid_file(data: Mapping[str, object]) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = PID_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(PID_FILE)


def _spawn(
    command: Iterable[str],
    log_path: Path,
    env: Mapping[str, str] | None = None,
) -> subprocess.Popen[bytes]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab", buffering=0) as log_file:
        process = subprocess.Popen(  # noqa: S603 - command list is explicit
            list(command),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=dict(env) if env else None,
        )
    return process


def show_status(console: Console) -> None:
    data = _load_pid_file(console)
    statuses = []
    for service in SERVICES:
        pid = data.get(service)
        if not isinstance(pid, int):
            statuses.append((service, "n/a", "missing"))
        else:
            alive = _alive(pid)
            statuses.append((service, str(pid), "alive" if alive else "stopped"))
    if all(state != "alive" for _, _, state in statuses):
        console.print("[yellow]PSD is not running.[/yellow]")
    else:
        table = Table(title="PSD Services", show_header=True, header_style="bold cyan")
        table.add_column("Service")
        table.add_column("PID")
        table.add_column("Status")
        for service, pid_text, state in statuses:
            color = "green" if state == "alive" else "red"
            table.add_row(service.title(), pid_text, f"[{color}]{state}[/{color}]")
        console.print(table)
    env_info = data.get("env")
    if isinstance(env_info, dict) and env_info:
        env_table = Table(title="PSD Environment", show_header=False, header_style="dim")
        env_table.add_column("Key", style="dim")
        env_table.add_column("Value")
        for key in ENV_SUMMARY_KEYS:
            value = env_info.get(key)
            if value is None:
                continue
            env_table.add_row(key, str(value))
        console.print(env_table)
    port = data.get("port", _port_from_env())
    console.print(f"Dashboard: http://127.0.0.1:{port}")


def show_logs(console: Console, lines: int = LOG_TAIL_LINES) -> None:
    if lines <= 0:
        console.print("[red]Log tail length must be positive.[/red]")
        return
    console.print(
        Panel.fit(
            f"Showing last {lines} line(s) from PSD logs in {RUN_DIR}",
            title="Logs",
            border_style="cyan",
        )
    )
    any_found = False
    for service in SERVICES:
        log_name = _LOG_NAMES.get(service)
        if not log_name:
            continue
        path = RUN_DIR / log_name
        console.rule(f"[bold]{service.title()} ({log_name})")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            console.print("[dim]Log file not found.[/dim]")
            continue
        except Exception as exc:  # pragma: no cover - defensive
            console.print(f"[red]Failed to read log: {exc}[/red]")
            continue
        lines_data = text.splitlines()
        tail = lines_data[-lines:] if lines < len(lines_data) else lines_data
        if not tail:
            console.print("[dim](empty log)[/dim]")
        else:
            any_found = True
            for entry in tail:
                console.print(entry)
    if not any_found:
        console.print("[yellow]No PSD log files found yet.[/yellow]")


def open_dashboard(console: Console) -> None:
    data = _load_pid_file()
    port = data.get("port", _port_from_env())
    url = f"http://127.0.0.1:{port}"
    success = webbrowser.open(url)
    if success:
        console.print(f"[green]Opened dashboard:[/green] {url}")
    else:
        console.print(f"[yellow]Attempted to open dashboard:[/yellow] {url}")


def start_psd(console: Console) -> None:
    state = _load_pid_file(console)
    port = _port_from_env()
    env_file = os.environ.get("PSD_ENV_FILE", ".env")
    env_loaded = _load_env_file(env_file)
    child_env = _with_defaults({**os.environ, **env_loaded})
    console.print(
        "[dim]Using {snapshot} | IB {host}:{port} clientId={client_id}[/]".format(
            snapshot=child_env["PSD_SNAPSHOT_FN"],
            host=child_env["IB_HOST"],
            port=child_env["IB_PORT"],
            client_id=child_env["IB_CLIENT_ID"],
        )
    )
    running: dict[str, int] = {}
    for service in SERVICES:
        pid = state.get(service)
        if isinstance(pid, int) and _alive(pid):
            console.print(f"[yellow]{service.title()} already running (PID {pid}).[/yellow]")
            running[service] = pid
    commands = {
        name: ([arg.format(port=port) for arg in cmd] if name == "web" else cmd)
        for name, cmd in _PROCESS_COMMANDS.items()
    }
    for service, cmd in commands.items():
        if service in running:
            continue
        log_path = RUN_DIR / _LOG_NAMES[service]
        console.print(f"[cyan]Starting {service} -> {' '.join(cmd)}[/cyan]")
        process = _spawn(cmd, log_path, env=child_env)
        running[service] = process.pid
        console.print(f"[green]{service.title()} PID {process.pid}[/green]")
    env_summary = {key: child_env.get(key) for key in ENV_SUMMARY_KEYS if child_env.get(key) is not None}
    data: dict[str, object] = {**running, "port": port, "env": env_summary}
    _save_pid_file(data)
    open_dashboard(console)
    time.sleep(0.2)
    show_status(console)


def _kill_with_sequence(pid: int, console: Console) -> bool:
    if not _alive(pid):
        return True
    for sig, wait_time in (
        (signal.SIGINT, 3.0),
        (signal.SIGTERM, 3.0),
        (getattr(signal, "SIGKILL", signal.SIGTERM), 0.0),
    ):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return True
        except PermissionError:
            console.print(f"[red]Permission denied when sending {sig.name} to PID {pid}.[/red]")
            return False
        if wait_time and _wait_for_exit(pid, wait_time):
            return True
        if not wait_time:
            return not _alive(pid)
    return not _alive(pid)


def stop_psd(console: Console) -> None:
    data = _load_pid_file(console)
    if not data:
        console.print("[yellow]No PSD processes tracked.[/yellow]")
        return
    if not any(key in data for key in SERVICES):
        console.print("[yellow]No PSD processes tracked.[/yellow]")
        if PID_FILE.exists():
            PID_FILE.unlink()
            console.print("[green]Cleared pid file.[/green]")
        return
    results: list[tuple[str, str]] = []
    for service in SERVICES:
        pid = data.get(service)
        if not isinstance(pid, int):
            results.append((service, "missing"))
            continue
        if not _alive(pid):
            results.append((service, "already stopped"))
            continue
        stopped = _kill_with_sequence(pid, console)
        results.append((service, "stopped" if stopped else "still running"))
    console.print("[bold]Stop results:[/bold]")
    for service, status in results:
        console.print(f"  - {service.title()}: {status}")
    remaining = {
        svc: data.get(svc)
        for svc in SERVICES
        if isinstance(data.get(svc), int) and _alive(int(data.get(svc)))
    }
    if remaining:
        port_value = data.get("port", _port_from_env())
        updated: dict[str, object] = {**remaining, "port": port_value}
        env_info = data.get("env")
        if isinstance(env_info, dict) and env_info:
            updated["env"] = env_info
        _save_pid_file(updated)
        console.print("[yellow]Some services are still running; pid file updated.[/yellow]")
    elif PID_FILE.exists():
        PID_FILE.unlink()
        console.print("[green]Cleared pid file.[/green]")


def _menu_panel() -> Panel:
    labels = [
        "[1] Status",
        "[2] Stop PSD",
        "[3] Open Dashboard",
        "[4] Start PSD",
        "[5] Tail Logs",
        "[q] Quit",
    ]
    lines = [escape(label) for label in labels]
    return Panel("\n".join(lines), title="PSD Ops Menu", border_style="cyan")


def main() -> None:
    console = Console()
    while True:
        console.print(_menu_panel())
        choice = console.input("Select option: ").strip().lower()
        if choice in {"q", "quit", "exit"}:
            break
        if choice == "1":
            show_status(console)
        elif choice == "2":
            stop_psd(console)
        elif choice == "3":
            open_dashboard(console)
        elif choice == "4":
            start_psd(console)
        elif choice == "5":
            show_logs(console)
        else:
            console.print("[red]Invalid selection. Choose 1-5 or q to quit.[/red]")


if __name__ == "__main__":
    main()
