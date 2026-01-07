from __future__ import annotations

"""Helpers to launch the Portfolio Sentinel Dashboard."""

import importlib
import os
import shlex
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

# Primary: Vite dev server (modern dashboard)
DEV_HOST, DEV_PORT = "localhost", 5173
# Fallback: PSD backend (FastAPI)
API_HOST, API_PORT = "127.0.0.1", 51127
MODULE_PATH = Path(__file__).resolve()
REPO_ROOT = MODULE_PATH.parents[2]
WEB_ROOT = REPO_ROOT / "apps" / "web"
DIST_INDEX = WEB_ROOT / "dist" / "index.html"
PSD_ENV_PATH = REPO_ROOT / ".psd.env"
_DASH_URL = f"http://{API_HOST}:{API_PORT}/psd"
_DEV_DASH_URL = f"http://{DEV_HOST}:{DEV_PORT}/psd"

_AUTO_STARTED = False
_DEFAULT_STARTUP_TIMEOUT_S = 20.0


def _is_dev_mode() -> bool:
    """Auto-detect if Vite dev server is running on port 5173."""
    # If explicitly set, respect it
    env_val = os.getenv("PSD_DEV_MODE", "").lower()
    if env_val in ("1", "true", "yes"):
        return True
    if env_val in ("0", "false", "no"):
        return False
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    # Auto-detect: check if Vite is running
    return _port_open(DEV_HOST, DEV_PORT)


def _build_uvicorn_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "--factory",
        "psd.web.server:make_app",
        "--host",
        API_HOST,
        "--port",
        str(API_PORT),
    ]


def _uvicorn_command_display() -> str:
    return shlex.join(_build_uvicorn_command())


def _format_start_failure(exit_code: int | None) -> str:
    code = f" (exit code {exit_code})" if exit_code is not None else ""
    return (
        "Portfolio Sentinel API failed to start"
        f"{code}. Try running `{_uvicorn_command_display()}` from the repo root for details."
    )


def _startup_timeout_s() -> float:
    raw = os.getenv("PSD_API_STARTUP_TIMEOUT_S")
    if raw is None:
        return _DEFAULT_STARTUP_TIMEOUT_S
    try:
        timeout = float(raw)
    except ValueError:
        return _DEFAULT_STARTUP_TIMEOUT_S
    return max(timeout, 1.0)


def _notify_psd_error(status: Any, message: str) -> None:
    if status:
        try:
            status.update("Portfolio Sentinel failed", "red")
            console = getattr(status, "console", None)
            if console is not None:
                console.print(f"[red]{message}[/]")
                return
        except Exception:
            pass
    print(message)


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Check if a port is open, trying both IPv4 and IPv6."""
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                # For IPv6 localhost, use ::1
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


def _ensure_uvicorn_runtime() -> None:
    """Install uvicorn runtime deps if they are missing."""

    missing: list[str] = []
    for module_name, package_name in ("uvicorn", "uvicorn"), ("click", "click"):
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            missing.append(package_name)
    if not missing:
        return
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", *missing],
        cwd=str(REPO_ROOT),
    )


def _load_psd_env() -> dict[str, str]:
    """Load environment overrides from .psd.env if present."""

    if not PSD_ENV_PATH.exists():
        return {}

    overrides: dict[str, str] = {}
    try:
        content = PSD_ENV_PATH.read_text(encoding="utf-8")
    except OSError:
        return overrides
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip("\"'")
        overrides[key] = value
    return overrides


def start_psd_dashboard() -> None:
    """Build the PSD web bundle if needed, ensure the API is live, and open /psd."""

    if not DIST_INDEX.exists():
        subprocess.check_call(["npm", "ci"], cwd=str(WEB_ROOT))
        subprocess.check_call(["npm", "run", "build"], cwd=str(WEB_ROOT))

    if _port_open(API_HOST, API_PORT):
        _open_dash_tab()
        return

    _ensure_uvicorn_runtime()
    env = os.environ.copy()
    env.update(_load_psd_env())
    proc = subprocess.Popen(
        _build_uvicorn_command(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        cwd=str(REPO_ROOT),
        env=env,
    )

    timeout_s = _startup_timeout_s()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _port_open(API_HOST, API_PORT):
            break
        if proc.poll() is not None:
            raise RuntimeError(_format_start_failure(proc.returncode))
        time.sleep(0.2)
    else:
        if proc.poll() is not None:
            raise RuntimeError(_format_start_failure(proc.returncode))
        raise TimeoutError(
            "Timed out waiting "
            f"({timeout_s:.1f}s) for Portfolio Sentinel API on {API_HOST}:{API_PORT}. "
            f"Run `{_uvicorn_command_display()}` for diagnostics or set "
            "PSD_API_STARTUP_TIMEOUT_S to increase the wait."
        )

    if not _port_open(API_HOST, API_PORT):
        raise RuntimeError(
            "Portfolio Sentinel API did not respond after startup. Check for firewall blocks or port conflicts."
        )

    _open_dash_tab()


def _open_dash_tab() -> None:
    url = _DEV_DASH_URL if _is_dev_mode() else _DASH_URL
    webbrowser.open_new_tab(url)


def launch(status: Any, fmt: str) -> None:  # noqa: ARG001 - fmt reserved for future
    """Entry point used by the main menu to open the PSD dashboard."""

    global _AUTO_STARTED

    if status:
        try:
            status.update("Opening Portfolio Sentinel Dashboard", "cyan")
        except Exception:  # pragma: no cover - defensive: status may not support update
            pass

    try:
        if _is_dev_mode():
            # In dev mode, just open the Vite dev server directly
            _open_dash_tab()
        elif not _AUTO_STARTED or not _port_open(API_HOST, API_PORT):
            _AUTO_STARTED = True
            start_psd_dashboard()
        else:
            _open_dash_tab()
    except Exception as exc:  # pragma: no cover - surfaced to the user below
        _AUTO_STARTED = False
        _notify_psd_error(status, str(exc))
    else:
        if status:
            try:
                status.update("Ready", "green")
            except Exception:  # pragma: no cover
                pass
