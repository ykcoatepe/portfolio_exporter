"""Small helpers for consistent JSON summaries."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping


SCHEMA_VERSION = "1.0.0"


def _base(
    outputs: Mapping[str, str],
    warnings: List[str] | None,
    meta: Dict[str, Any] | None,
) -> Dict[str, Any]:
    # Normalize outputs to a list of written file paths.
    # When JSON-only or no files were written, "outputs" is an empty list.
    out_list = [p for p in outputs.values() if p]
    return {
        "ok": True,
        "outputs": out_list,
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

    meta = {**(meta or {}), "schema_id": "time_series_summary", "schema_version": SCHEMA_VERSION}
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

    meta = {**(meta or {}), "schema_id": "report_summary", "schema_version": SCHEMA_VERSION}
    base = _base(outputs, warnings, meta)
    base.update({"sections": dict(sections)})
    return base
