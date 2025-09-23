# SPDX-License-Identifier: MIT

"""Background refresh helpers for live quote/greeks updates."""

from __future__ import annotations

import os
import threading
from typing import Callable, Optional


class RefreshLoop:
    """Small helper that executes a callable on a fixed cadence."""

    def __init__(
        self,
        tick: Callable[[], None],
        interval_s: Optional[float] = None,
        *,
        env_var: str = "PSD_REFRESH_INTERVAL_S",
    ) -> None:
        self._tick = tick
        self._interval = _resolve_interval(env_var, interval_s)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Begin invoking the tick callback every configured interval."""

        if self._interval <= 0.0:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="psd-refresh", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the loop to stop after the current sleep completes."""

        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._tick()
            except Exception:  # pragma: no cover - defensive
                # Swallow refresh errors to keep the API responsive.
                continue


def _resolve_interval(env_var: str, fallback: Optional[float]) -> float:
    env_value = os.getenv(env_var)
    if env_value is not None:
        try:
            return float(env_value)
        except ValueError:
            pass
    if fallback is not None:
        return float(fallback)
    return 15.0
