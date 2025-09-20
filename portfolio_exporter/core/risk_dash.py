from __future__ import annotations

import sys
import threading
import time
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.table import Table

from portfolio_exporter.scripts import risk_watch


def _render(metrics: dict[str, Any]) -> Table:
    table = Table(title="Risk Dashboard")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, val in metrics.items():
        table.add_row(key, str(val))
    return table


def _spawn_back_listener(stop_event: threading.Event) -> threading.Thread | None:
    """Spawn a background line-input listener that sets stop_event on 'b'.

    Returns the Thread if created, else None. Only starts when stdin is a TTY.
    """
    try:
        if not sys.stdin.isatty():  # non-interactive; don't attempt input
            return None
    except Exception:
        return None

    def _worker() -> None:
        try:
            while not stop_event.is_set():
                try:
                    s = input()
                except EOFError:
                    break
                except Exception:
                    break
                if s is None:
                    break
                if s.strip().lower() in {"b", "back"}:
                    stop_event.set()
                    break
        finally:
            # nothing to clean up; event communicates shutdown
            pass

    t = threading.Thread(target=_worker, name="riskdash-back-listener", daemon=True)
    t.start()
    return t


def run(
    refresh: float = 5.0,
    iterations: int | None = None,
    enable_back_key: bool = True,
) -> None:
    """Display risk metrics in real-time using Rich.

    - Press Ctrl-C to return to the previous menu.
    - Optional: limit updates via `iterations` for non-interactive callers.
    """

    console = Console()
    count = 0
    # fetch and render initial metrics immediately
    metrics = risk_watch.run(return_dict=True) or {}
    table = _render(metrics)
    hint = (
        "[dim]Press 'b' then Enter or Ctrl-C to go back[/]"
        if enable_back_key
        else "[dim]Press Ctrl-C to go back[/]"
    )
    console.print(hint)

    stop_event: threading.Event = threading.Event()
    listener: threading.Thread | None = None
    if enable_back_key:
        listener = _spawn_back_listener(stop_event)

    with Live(table, console=console, refresh_per_second=4) as live:
        try:
            while True:
                count += 1
                if stop_event.is_set():
                    break
                if iterations is not None and count >= iterations:
                    break
                time.sleep(refresh)
                metrics = risk_watch.run(return_dict=True) or {}
                live.update(_render(metrics))
        except KeyboardInterrupt:
            # Gracefully return control to the calling menu
            pass
        finally:
            # Signal listener to end and join briefly
            stop_event.set()
            if listener is not None and listener.is_alive():
                listener.join(timeout=0.2)
