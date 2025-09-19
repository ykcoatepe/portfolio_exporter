"""Small helpers for consistent JSON summaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "1.0.0"


def _base(
    outputs: Mapping[str, str],
    warnings: list[str] | None,
    meta: dict[str, Any] | None,
) -> dict[str, Any]:
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
    warnings: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standardised summary for time‑series exports."""

    meta = {**(meta or {}), "schema_id": "time_series_summary", "schema_version": SCHEMA_VERSION}
    base = _base(outputs, warnings, meta)
    base.update({"rows": rows, "start": start, "end": end})
    return base


def report_summary(
    sections: Mapping[str, int],
    outputs: Mapping[str, str],
    warnings: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a summary for multi‑section reports."""

    meta = {**(meta or {}), "schema_id": "report_summary", "schema_version": SCHEMA_VERSION}
    base = _base(outputs, warnings, meta)
    base.update({"sections": dict(sections)})
    return base
