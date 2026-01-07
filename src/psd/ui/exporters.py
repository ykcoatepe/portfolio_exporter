"""Exporter helpers for PSD API responses."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from typing import Literal

FIELDNAMES = [
    "date",
    "hy",
    "vx1",
    "vx2",
    "z_hy",
    "term_ratio",
    "cal_spread_pct",
    "cal_spread_abs",
    "saturated",
    "hy_score",
    "vix_score",
    "msb",
    "color",
    "triggers",
    "winsor_clipped_n",
    "cooldown_until",
]

MediaType = Literal["csv", "parquet"]


def _normalize_triggers(value: object, *, for_parquet: bool) -> list[str] | str:
    if for_parquet:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if item not in (None, ""))
    return str(value)


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def export_snapshot(
    rows: Sequence[Mapping[str, object]] | Sequence[dict[str, object]],
    *,
    fmt: MediaType = "csv",
    filename: str = "msb_history",
) -> tuple[bytes, str, str]:
    """Serialize MSB history payloads to CSV or Parquet.

    Returns a tuple of ``(content_bytes, media_type, filename)`` where
    ``filename`` already includes the appropriate extension.
    """

    fmt = fmt.lower()  # normalise early
    if fmt not in ("csv", "parquet"):
        raise ValueError(f"Unsupported export format: {fmt}")

    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=FIELDNAMES)
        writer.writeheader()
        for entry in rows:
            row = {key: entry.get(key) for key in FIELDNAMES}
            row["triggers"] = _normalize_triggers(
                row.get("triggers"), for_parquet=False
            )
            writer.writerow({key: _csv_value(value) for key, value in row.items()})
        content = buffer.getvalue().encode("utf-8")
        return content, "text/csv; charset=utf-8", f"{filename}.csv"

    # Parquet path (lazy pandas import to avoid import cost on CLI startup)
    import pandas as pd  # type: ignore

    normalized: list[dict[str, object]] = []
    for entry in rows:
        row = {key: entry.get(key) for key in FIELDNAMES}
        row["triggers"] = _normalize_triggers(row.get("triggers"), for_parquet=True)
        normalized.append(row)

    frame = pd.DataFrame(normalized, columns=FIELDNAMES)
    buffer = io.BytesIO()
    frame.to_parquet(buffer, index=False)
    return buffer.getvalue(), "application/octet-stream", f"{filename}.parquet"


__all__ = ["export_snapshot", "FIELDNAMES"]

# TODO: fill in at v0.1
