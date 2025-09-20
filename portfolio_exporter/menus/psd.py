from __future__ import annotations

"""Helpers to launch the Portfolio Sentinel Dashboard."""

import socket
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any

API_HOST, API_PORT = "127.0.0.1", 8000


def _port_open(host: str, port: int, timeout: float = 0.2) -> bool:
    with socket.socket() as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def start_psd_dashboard() -> None:
    """Build the PSD web bundle if needed, ensure the API is live, and open /psd."""

    dist = Path("apps/web/dist")
    if not dist.exists() or not any(dist.rglob("index.html")):
        subprocess.check_call(["npm", "ci"], cwd="apps/web")
        subprocess.check_call(["npm", "run", "build"], cwd="apps/web")

    if not _port_open(API_HOST, API_PORT):
        subprocess.Popen(
            [
                "python3",
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
        )
        for _ in range(25):
            if _port_open(API_HOST, API_PORT):
                break
            time.sleep(0.2)

    webbrowser.open_new_tab(f"http://{API_HOST}:{API_PORT}/psd")


def launch(status: Any, fmt: str) -> None:  # noqa: ARG001 - fmt reserved for future
    """Entry point used by the main menu to open the PSD dashboard."""

    if status:
        try:
            status.update("Opening Portfolio Sentinel Dashboard", "cyan")
        except Exception:  # pragma: no cover - defensive: status may not support update
            pass

    try:
        start_psd_dashboard()
    finally:
        if status:
            try:
                status.update("Ready", "green")
            except Exception:  # pragma: no cover
                pass
