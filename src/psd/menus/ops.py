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
  - IB_PORT          Unset by default -> Gateway (4001) with TWS fallback (7496).
                     Set explicitly for paper (4002/7497) or to disable fallback.

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
import socket
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

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_DIR = Path(os.getenv("PSD_RUN_DIR", "run"))
if not RUN_DIR.is_absolute():
    RUN_DIR = (REPO_ROOT / RUN_DIR).resolve()
PID_FILE = RUN_DIR / "psd-pids.json"
SERVICES = ("ingestor", "scanner", "web")
UI_SERVICE = "ui"
DEFAULT_PORT = 51127
WEB_ROOT = REPO_ROOT / "apps" / "web"
DIST_INDEX = WEB_ROOT / "dist" / "index.html"
DEV_HOST = "localhost"
try:
    DEV_PORT = int(os.getenv("PSD_DEV_PORT", "5173"))
except ValueError:
    DEV_PORT = 5173

_PROCESS_COMMANDS: Mapping[str, list[str]] = {
    "ingestor": [sys.executable, "-m", "psd.ingestor.main"],
    "scanner": [sys.executable, "-m", "psd.sentinel.scan"],
    "web": [
        sys.executable,
        "-m",
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
    UI_SERVICE: "ui.log",
}

LOG_TAIL_LINES = int(os.getenv("PSD_LOG_TAIL_LINES", "40"))

ENV_SUMMARY_KEYS: tuple[str, ...] = (
    "PSD_SNAPSHOT_FN",
    "PSD_RULES_FN",
    "IB_HOST",
    "IB_PORT",
    "IB_CLIENT_ID",
)


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Check if a port is open, trying both IPv4 and IPv6."""
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                addr = (
                    "::1"
                    if family == socket.AF_INET6 and host in ("localhost", "127.0.0.1")
                    else host
                )
                sock.connect((addr, port))
                return True
        except OSError:
            continue
    return False


def _ensure_uvicorn_runtime(console: Console) -> bool:
    """Install uvicorn runtime deps if they are missing."""
    missing: list[str] = []
    for module_name, package_name in ("uvicorn", "uvicorn"), ("click", "click"):
        try:
            __import__(module_name)
        except ModuleNotFoundError:
            missing.append(package_name)
    if not missing:
        return True
    console.print(
        f"[yellow]Missing runtime deps ({', '.join(missing)}); installing...[/yellow]"
    )
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", *missing],
            cwd=str(REPO_ROOT),
        )
    except subprocess.CalledProcessError as exc:
        console.print(
            f"[red]Failed to install runtime deps (exit {exc.returncode}).[/red]"
        )
        return False
    return True


def _dev_mode_requested(env: Mapping[str, str] | None = None) -> bool:
    """Return True when PSD_DEV_MODE explicitly enables dev server."""
    source = env if env is not None else os.environ
    env_val = str(source.get("PSD_DEV_MODE", "")).lower()
    return env_val in ("1", "true", "yes")


def _is_dev_mode() -> bool:
    """Return True when PSD_DEV_MODE is set or a Vite dev server is active."""
    if _dev_mode_requested():
        return True
    env_val = os.getenv("PSD_DEV_MODE", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    return _port_open(DEV_HOST, _dev_port_from_env())


def _dev_port_from_env(env: Mapping[str, str] | None = None) -> int:
    source = env if env is not None else os.environ
    raw = source.get("PSD_DEV_PORT", str(DEV_PORT))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return DEV_PORT


def _wait_for_port(host: str, port: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(0.1)
    return _port_open(host, port)


def _start_ui_dev_server(console: Console, env: Mapping[str, str]) -> int | None:
    """Start the Vite dev server when PSD_DEV_MODE=1."""
    dev_port = _dev_port_from_env(env)
    if _port_open(DEV_HOST, dev_port):
        return None
    console.print(
        f"[cyan]Starting PSD UI dev server on {DEV_HOST}:{dev_port} (bun).[/cyan]"
    )
    try:
        process = _spawn(
            [
                "bun",
                "run",
                "dev",
                "--",
                "--host",
                DEV_HOST,
                "--port",
                str(dev_port),
            ],
            RUN_DIR / _LOG_NAMES[UI_SERVICE],
            env=env,
            cwd=WEB_ROOT,
        )
    except FileNotFoundError:
        console.print(
            "[red]bun not found. Run `cd apps/web && bun install && bun run dev`.[/red]"
        )
        return None
    if not _wait_for_port(DEV_HOST, dev_port):
        console.print(
            f"[yellow]PSD UI dev server did not respond on {DEV_HOST}:{dev_port} yet.[/yellow]"
        )
    return process.pid


def _ensure_frontend_build(console: Console) -> bool:
    """Ensure the React bundle exists for /psd."""
    if DIST_INDEX.exists():
        return True
    console.print(
        "[yellow]PSD UI bundle missing; building via bun (apps/web).[/yellow]"
    )
    try:
        subprocess.check_call(["bun", "install"], cwd=str(WEB_ROOT))
        subprocess.check_call(["bun", "run", "build"], cwd=str(WEB_ROOT))
    except FileNotFoundError:
        console.print(
            "[red]bun not found. Run `cd apps/web && bun install && bun run build`.[/red]"
        )
        return False
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]PSD UI build failed (exit {exc.returncode}).[/red]")
        return False
    return DIST_INDEX.exists()


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
    # Prefer IBKR + FRED with Yahoo fallbacks for MSB vendor seeding.
    out.setdefault("MSB_SOURCE", "ibkr")
    # IB_PORT intentionally NOT set to allow Gateway->TWS auto-fallback.
    # For paper, set IB_PORT=4002 or IB_PORT=7497 in .env.
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
    # Treat zombie/defunct processes as not alive so we can restart cleanly.
    try:
        import psutil  # type: ignore

        proc = psutil.Process(pid)
        if proc.status() == psutil.STATUS_ZOMBIE:
            return False
    except Exception:
        try:
            output = subprocess.check_output(
                ["ps", "-o", "stat=", "-p", str(pid)],
                text=True,
            ).strip()
            if "Z" in output:
                return False
        except Exception:
            pass
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
        elif key in SERVICES or key == UI_SERVICE:
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
    cwd: Path | None = None,
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
            cwd=str(cwd) if cwd else None,
            start_new_session=True,
        )
    return process


_MSB_VENDOR_REQUIRED = ("hy.csv", "vx1.csv", "vx2.csv")


def _missing_vendor_files(vendor_root: Path) -> list[str]:
    missing: list[str] = []
    for name in _MSB_VENDOR_REQUIRED:
        path = vendor_root / name
        try:
            if not path.exists() or path.stat().st_size == 0:
                missing.append(name)
        except OSError:
            missing.append(name)
    return missing


def _seed_vendor_data_if_needed(console: Console, env: Mapping[str, str]) -> None:
    vendor_root = REPO_ROOT / "data" / "vendor"
    missing = _missing_vendor_files(vendor_root)
    if not missing:
        return
    console.print(
        f"[yellow]MSB vendor data missing ({', '.join(missing)}); seeding now...[/yellow]"
    )
    try:
        from psd.datasources.msb_vendor import refresh_vendor_data

        status = refresh_vendor_data(vendor_root, env=env)
    except Exception as exc:  # pragma: no cover - depends on runtime IO
        console.print(f"[red]MSB vendor seed failed: {exc}[/red]")
        return
    missing_after = _missing_vendor_files(vendor_root)
    if missing_after:
        hint = ""
        if "hy.csv" in missing_after and not env.get("FRED_API_KEY"):
            hint = " (set FRED_API_KEY for HY data)"
        console.print(
            "[red]MSB vendor seed incomplete; missing "
            f"{', '.join(missing_after)}{hint}[/red]"
        )
        return
    console.print(f"[green]MSB vendor data ready.[/green] {status}")


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
    ui_pid = data.get(UI_SERVICE)
    if isinstance(ui_pid, int):
        statuses.append(
            (UI_SERVICE, str(ui_pid), "alive" if _alive(ui_pid) else "stopped")
        )
    elif _is_dev_mode():
        statuses.append((UI_SERVICE, "n/a", "external"))
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
        env_table = Table(
            title="PSD Environment", show_header=False, header_style="dim"
        )
        env_table.add_column("Key", style="dim")
        env_table.add_column("Value")
        for key in ENV_SUMMARY_KEYS:
            value = env_info.get(key)
            if value is None:
                continue
            env_table.add_row(key, str(value))
        console.print(env_table)
    port = data.get("port", _port_from_env())
    console.print(f"Dashboard: http://127.0.0.1:{port}/psd")
    if _is_dev_mode():
        console.print(f"UI (dev): http://{DEV_HOST}:{_dev_port_from_env()}/psd")


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
    # Prefer Vite dev server when available, otherwise serve the built bundle via FastAPI.
    if _is_dev_mode():
        dev_port = _dev_port_from_env()
        url = f"http://{DEV_HOST}:{dev_port}/psd"
        console.print(
            "[cyan]Opening Vite dev server (PSD_DEV_MODE=1 or detected).[/cyan]"
        )
    else:
        _ensure_frontend_build(console)
        data = _load_pid_file()
        port = data.get("port", _port_from_env())
        url = f"http://127.0.0.1:{port}/psd"
    success = webbrowser.open(url)
    if success:
        console.print(f"[green]Opened dashboard:[/green] {url}")
    else:
        console.print(f"[yellow]Attempted to open dashboard:[/yellow] {url}")


def open_dashboard_when_ready(console: Console, timeout: float = 15.0) -> None:
    """Wait for the PSD web server (user mode) before opening the dashboard."""
    if _is_dev_mode():
        open_dashboard(console)
        return
    port = _port_from_env()
    if _wait_for_port("127.0.0.1", port, timeout=timeout):
        open_dashboard(console)
        return
    console.print(
        f"[yellow]PSD web server still not responding on 127.0.0.1:{port}.[/yellow]"
    )
    console.print(f"[cyan]Open manually: http://127.0.0.1:{port}/psd[/cyan]")


def start_psd(
    console: Console,
    mode: str | None = None,
    *,
    open_browser: bool = True,
) -> None:
    state = _load_pid_file(console)
    port = _port_from_env()
    env_file = os.environ.get("PSD_ENV_FILE")
    if not env_file:
        env_file = ".psd.env" if Path(".psd.env").exists() else ".env"
    env_loaded = _load_env_file(env_file)
    child_env = _with_defaults({**os.environ, **env_loaded})
    src_path = str(REPO_ROOT / "src")
    pythonpath = child_env.get("PYTHONPATH", "")
    if src_path not in pythonpath.split(os.pathsep):
        child_env["PYTHONPATH"] = (
            os.pathsep.join([src_path, pythonpath]) if pythonpath else src_path
        )
    if mode == "dev":
        child_env["PSD_DEV_MODE"] = "1"
    elif mode == "user":
        child_env["PSD_DEV_MODE"] = "0"
    for key in ("PSD_DEV_MODE", "PSD_DEV_PORT"):
        if key in child_env:
            os.environ[key] = str(child_env[key])
    _seed_vendor_data_if_needed(console, child_env)
    console.print(
        "[dim]Using {snapshot} | IB {host}:{port} clientId={client_id}[/]".format(
            snapshot=child_env["PSD_SNAPSHOT_FN"],
            host=child_env["IB_HOST"],
            port=child_env.get("IB_PORT", "auto"),
            client_id=child_env["IB_CLIENT_ID"],
        )
    )
    if not _ensure_uvicorn_runtime(console):
        console.print(
            "[red]PSD web server prerequisites missing. Aborting start.[/red]"
        )
        return
    running: dict[str, int] = {}
    if _dev_mode_requested(child_env):
        ui_pid = state.get(UI_SERVICE)
        if isinstance(ui_pid, int) and _alive(ui_pid):
            running[UI_SERVICE] = ui_pid
        else:
            ui_pid = _start_ui_dev_server(console, child_env)
            if ui_pid:
                running[UI_SERVICE] = ui_pid
    for service in SERVICES:
        pid = state.get(service)
        if isinstance(pid, int) and _alive(pid):
            if service == "web" and not _port_open("127.0.0.1", port):
                console.print(
                    "[yellow]Web process alive but port is closed; restarting web.[/yellow]"
                )
            else:
                console.print(
                    f"[yellow]{service.title()} already running (PID {pid}).[/yellow]"
                )
                running[service] = pid
                continue
    commands = {
        name: ([arg.format(port=port) for arg in cmd] if name == "web" else cmd)
        for name, cmd in _PROCESS_COMMANDS.items()
    }
    for service, cmd in commands.items():
        if service in running:
            continue
        log_path = RUN_DIR / _LOG_NAMES[service]
        console.print(f"[cyan]Starting {service} -> {' '.join(cmd)}[/cyan]")
        process = _spawn(cmd, log_path, env=child_env, cwd=REPO_ROOT)
        running[service] = process.pid
        console.print(f"[green]{service.title()} PID {process.pid}[/green]")
    env_summary = {
        key: child_env.get(key)
        for key in ENV_SUMMARY_KEYS
        if child_env.get(key) is not None
    }
    data: dict[str, object] = {**running, "port": port, "env": env_summary}
    _save_pid_file(data)
    if not _wait_for_port("127.0.0.1", port, timeout=6.0):
        console.print(
            f"[yellow]PSD web server not responding on 127.0.0.1:{port} yet.[/yellow]"
        )
    if open_browser:
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
            console.print(
                f"[red]Permission denied when sending {sig.name} to PID {pid}.[/red]"
            )
            return False
        if wait_time and _wait_for_exit(pid, wait_time):
            return True
        if not wait_time:
            return not _alive(pid)
    return not _alive(pid)


def _pids_listening_on_port(port: int) -> list[int]:
    try:
        import psutil  # type: ignore

        pids: set[int] = set()
        for conn in psutil.net_connections(kind="inet"):
            if not conn.laddr:
                continue
            if conn.laddr.port != port:
                continue
            if conn.status != psutil.CONN_LISTEN:
                continue
            if conn.pid:
                pids.add(int(conn.pid))
        return sorted(pids)
    except Exception:
        pass

    try:
        output = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    pids = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return sorted(set(pids))


def _kill_port_listeners(port: int, console: Console) -> None:
    pids = _pids_listening_on_port(port)
    if not pids:
        return
    console.print(
        f"[yellow]Found {len(pids)} listener(s) on port {port}; forcing shutdown.[/yellow]"
    )
    for pid in pids:
        _kill_with_sequence(pid, console)


def stop_psd(console: Console, force_port_kill: bool = False) -> None:
    data = _load_pid_file(console)
    if not data:
        console.print("[yellow]No PSD processes tracked.[/yellow]")
        if force_port_kill:
            _kill_port_listeners(_port_from_env(), console)
        return
    if not any(key in data for key in SERVICES) and UI_SERVICE not in data:
        console.print("[yellow]No PSD processes tracked.[/yellow]")
        if PID_FILE.exists():
            PID_FILE.unlink()
            console.print("[green]Cleared pid file.[/green]")
        if force_port_kill:
            _kill_port_listeners(_port_from_env(), console)
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
    ui_pid = data.get(UI_SERVICE)
    if isinstance(ui_pid, int):
        if not _alive(ui_pid):
            results.append((UI_SERVICE, "already stopped"))
        else:
            stopped = _kill_with_sequence(ui_pid, console)
            results.append((UI_SERVICE, "stopped" if stopped else "still running"))
    console.print("[bold]Stop results:[/bold]")
    for service, status in results:
        console.print(f"  - {service.title()}: {status}")
    remaining = {
        svc: data.get(svc)
        for svc in SERVICES
        if isinstance(data.get(svc), int) and _alive(int(data.get(svc)))
    }
    if isinstance(ui_pid, int) and _alive(ui_pid):
        remaining[UI_SERVICE] = ui_pid
    if force_port_kill:
        port_value = data.get("port", _port_from_env())
        _kill_port_listeners(int(port_value), console)
        remaining = {
            svc: data.get(svc)
            for svc in SERVICES
            if isinstance(data.get(svc), int) and _alive(int(data.get(svc)))
        }
        if isinstance(ui_pid, int) and _alive(ui_pid):
            remaining[UI_SERVICE] = ui_pid
    if remaining:
        port_value = data.get("port", _port_from_env())
        updated: dict[str, object] = {**remaining, "port": port_value}
        env_info = data.get("env")
        if isinstance(env_info, dict) and env_info:
            updated["env"] = env_info
        _save_pid_file(updated)
        console.print(
            "[yellow]Some services are still running; pid file updated.[/yellow]"
        )
    elif PID_FILE.exists():
        PID_FILE.unlink()
        console.print("[green]Cleared pid file.[/green]")


def _menu_panel() -> Panel:
    labels = [
        "[1] Status",
        "[2] Stop PSD",
        "[3] Open Dashboard",
        "[4] Start PSD (User mode)",
        "[5] Start PSD (Dev mode)",
        "[6] Tail Logs",
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
            start_psd(console, mode="user")
        elif choice == "5":
            start_psd(console, mode="dev")
        elif choice == "6":
            show_logs(console)
        else:
            console.print("[red]Invalid selection. Choose 1-6 or q to quit.[/red]")


if __name__ == "__main__":
    main()
