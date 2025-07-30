from __future__ import annotations

import time
from typing import Any, Dict, Optional

from rich.console import Console
from rich.live import Live
from rich.table import Table

from portfolio_exporter.scripts import risk_watch


def _render(metrics: Dict[str, Any]) -> Table:
    table = Table(title="Risk Dashboard")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, val in metrics.items():
        table.add_row(key, str(val))
    return table


def run(refresh: float = 5.0, iterations: Optional[int] = None) -> None:
    """Display risk metrics in real-time using Rich."""

    console = Console()
    count = 0
    with Live(console=console, refresh_per_second=4) as live:
        while True:
            metrics = risk_watch.run(return_dict=True) or {}
            live.update(_render(metrics))
            count += 1
            if iterations is not None and count >= iterations:
                break
            time.sleep(refresh)
