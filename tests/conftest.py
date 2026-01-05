"""Shared pytest configuration for portfolio_exporter tests."""

from __future__ import annotations

import atexit
import asyncio
import contextlib
import os
import threading

os.environ.setdefault("PE_QUIET", "1")
os.environ.setdefault("PE_TEST_MODE", "1")
os.environ.setdefault("MOMO_OFFLINE", "1")
os.environ.setdefault("MOMO_DATA_MODE", "offline")
os.environ.setdefault("MPLBACKEND", "Agg")

try:
    asyncio.get_running_loop()
except RuntimeError:
    with contextlib.suppress(Exception):
        asyncio.set_event_loop(asyncio.new_event_loop())

with contextlib.suppress(Exception):
    import matplotlib

    matplotlib.use("Agg", force=True)
    with contextlib.suppress(Exception):
        import matplotlib.pyplot as plt

        def _noop_show(*_args, **_kwargs) -> None:
            """Avoid GUI waits in test environments."""

            return None

        plt.show = _noop_show  # type: ignore[assignment]

with contextlib.suppress(Exception):
    from src.psd.datasources import yfin as _yfin

    def _offline_fill(symbols: list[str]) -> dict[str, float | None]:
        """Prevent live Yahoo Finance lookups during tests."""

        return {sym.strip().upper(): None for sym in symbols if sym}

    _yfin.fill_equity_marks_from_yf = _offline_fill  # type: ignore[assignment]


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
