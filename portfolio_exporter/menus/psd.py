from __future__ import annotations

"""Helpers to launch the Portfolio Sentinel Dashboard."""

import importlib
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

API_HOST, API_PORT = "127.0.0.1", 8000
MODULE_PATH = Path(__file__).resolve()
REPO_ROOT = MODULE_PATH.parents[2]
WEB_ROOT = REPO_ROOT / "apps" / "web"
DIST_INDEX = WEB_ROOT / "dist" / "index.html"
_DASH_URL = f"http://{API_HOST}:{API_PORT}/psd"

_AUTO_STARTED = False


def _port_open(host: str, port: int, timeout: float = 0.2) -> bool:
    with socket.socket() as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            return True
        except OSError:
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


def start_psd_dashboard() -> None:
    """Build the PSD web bundle if needed, ensure the API is live, and open /psd."""

    if not DIST_INDEX.exists():
        subprocess.check_call(["npm", "ci"], cwd=str(WEB_ROOT))
        subprocess.check_call(["npm", "run", "build"], cwd=str(WEB_ROOT))

    if not _port_open(API_HOST, API_PORT):
        _ensure_uvicorn_runtime()
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "apps.api.main:app",
                "--host",
                API_HOST,
                "--port",
                str(API_PORT),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            cwd=str(REPO_ROOT),
        )
        for _ in range(25):
            if _port_open(API_HOST, API_PORT):
                break
            time.sleep(0.2)

    _open_dash_tab()


def _open_dash_tab() -> None:
    webbrowser.open_new_tab(_DASH_URL)


def launch(status: Any, fmt: str) -> None:  # noqa: ARG001 - fmt reserved for future
    """Entry point used by the main menu to open the PSD dashboard."""

    global _AUTO_STARTED

    if status:
        try:
            status.update("Opening Portfolio Sentinel Dashboard", "cyan")
        except Exception:  # pragma: no cover - defensive: status may not support update
            pass

    try:
        if not _AUTO_STARTED or not _port_open(API_HOST, API_PORT):
            _AUTO_STARTED = True
            start_psd_dashboard()
        else:
            _open_dash_tab()
    finally:
        if status:
            try:
                status.update("Ready", "green")
            except Exception:  # pragma: no cover
                pass
