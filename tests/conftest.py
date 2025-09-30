"""Shared pytest configuration for portfolio_exporter tests."""

from __future__ import annotations

import atexit
import os
import threading

os.environ.setdefault("PE_QUIET", "1")
os.environ.setdefault("MOMO_OFFLINE", "1")
os.environ.setdefault("MOMO_DATA_MODE", "offline")


@atexit.register
def _thread_report() -> None:
    """Warn when tests leave non-daemon threads running."""
    zombies = [
        t
        for t in threading.enumerate()
        if t.is_alive() and t.name != "MainThread" and not t.daemon
    ]
    if zombies:
        print("WARNING: Non-daemon threads still alive:", [t.name for t in zombies])
