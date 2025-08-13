"""Small helpers for consistent JSON summaries."""
from __future__ import annotations

from typing import Dict, List, Mapping, Any


def _base(outputs: Mapping[str, str], warnings: List[str] | None, meta: Dict[str, Any] | None) -> Dict[str, Any]:
    return {
        "ok": True,
        "outputs": {k: v for k, v in outputs.items()},
        "warnings": warnings or [],
        "meta": meta or {},
    }


def time_series_summary(
    rows: int,
    start: str | None,
    end: str | None,
    outputs: Mapping[str, str],
    warnings: List[str] | None = None,
    meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a standardised summary for time‑series exports."""

    base = _base(outputs, warnings, meta)
    base.update({"rows": rows, "start": start, "end": end})
    return base


def report_summary(
    sections: Mapping[str, int],
    outputs: Mapping[str, str],
    warnings: List[str] | None = None,
    meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a summary for multi‑section reports."""

    base = _base(outputs, warnings, meta)
    base.update({"sections": dict(sections)})
    return base
