from __future__ import annotations

from prometheus_client import Counter

MSB_SCHEDULER_RUNS = Counter(
    "psd_msb_scheduler_runs_total", "Daily MSB scheduler executions"
)

MSB_ALERTS = Counter(
    "psd_msb_alerts_total", "MSB alerts emitted", ["rule"]
)

LIVEBAR_ROWS = Counter(
    "psd_livebar_rows_total", "Live Status Bar rows written"
)

__all__ = ["MSB_SCHEDULER_RUNS", "MSB_ALERTS", "LIVEBAR_ROWS"]

