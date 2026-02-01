from __future__ import annotations

from prometheus_client import REGISTRY, Counter, Gauge

MSB_SCHEDULER_RUNS = Counter(
    "psd_msb_scheduler_runs_total", "Daily MSB scheduler executions"
)

MSB_ALERTS = Counter("psd_msb_alerts_total", "MSB alerts emitted", ["rule"])

LIVEBAR_ROWS = Counter("psd_livebar_rows_total", "Live Status Bar rows written")


def _gauge(name: str, help_text: str) -> Gauge:
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Gauge(name, help_text, registry=REGISTRY)


MSB_DATA_AGE_SECONDS = _gauge(
    "psd_msb_data_age_seconds",
    "Age in seconds of the most recent MSB reading (wall clock)",
)
__all__ = [
    "MSB_SCHEDULER_RUNS",
    "MSB_ALERTS",
    "LIVEBAR_ROWS",
    "MSB_DATA_AGE_SECONDS",
]
