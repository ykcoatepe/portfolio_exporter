# SPDX-License-Identifier: MIT

"""CSV ingestion helpers for live portfolio artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

import logging

logger = logging.getLogger(__name__)

_POSITIONS_PATTERN = "live_positions_*.csv"
_QUOTES_PATTERN = "live_quotes_*.csv"
_GREEKS_FILE = "portfolio_greeks_totals.csv"


@dataclass(frozen=True)
class CsvLoadResult:
    positions: list[dict[str, Any]]
    quotes: list[dict[str, Any]]
    metadata: dict[str, Any]

    @property
    def has_data(self) -> bool:
        return bool(self.positions or self.quotes)


def load_latest_positions(base_dir: Path | str) -> pd.DataFrame:
    """Load the newest live positions CSV if present."""

    return _load_latest(base_dir, _POSITIONS_PATTERN)


def load_latest_quotes(base_dir: Path | str) -> pd.DataFrame:
    """Load the newest live quotes CSV if present."""

    return _load_latest(base_dir, _QUOTES_PATTERN)


def load_latest_greeks_totals(base_dir: Path | str) -> pd.DataFrame:
    """Load the portfolio greeks totals file if present."""

    path = _coerce_path(base_dir) / _GREEKS_FILE
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_csv_records(base_dir: Path | str) -> CsvLoadResult:
    """Return normalized position/quote records from CSV artifacts."""

    directory = _coerce_path(base_dir)
    positions_path = _latest_file(directory, _POSITIONS_PATTERN)
    quotes_path = _latest_file(directory, _QUOTES_PATTERN)
    greeks_path = directory / _GREEKS_FILE if (directory / _GREEKS_FILE).exists() else None

    positions_df = _read_csv(positions_path)
    quotes_df = _read_csv(quotes_path)
    greeks_df = _read_csv(greeks_path)

    positions = _normalize_positions(positions_df, greeks_df)
    quotes = _normalize_quotes(quotes_df)

    metadata = {
        "data_root": str(directory),
        "positions_path": str(positions_path) if positions_path else None,
        "positions_rows": int(len(positions_df)) if positions_df is not None else 0,
        "quotes_path": str(quotes_path) if quotes_path else None,
        "quotes_rows": int(len(quotes_df)) if quotes_df is not None else 0,
        "greeks_path": str(greeks_path) if greeks_path else None,
        "greeks_rows": int(len(greeks_df)) if greeks_df is not None else 0,
    }

    if metadata["positions_path"]:
        logger.info(
            "Loaded positions CSV %s rows=%d", metadata["positions_path"], metadata["positions_rows"]
        )
    else:
        logger.debug("No positions CSV found under %s", directory)
    if metadata["quotes_path"]:
        logger.info("Loaded quotes CSV %s rows=%d", metadata["quotes_path"], metadata["quotes_rows"])
    else:
        logger.debug("No quotes CSV found under %s", directory)
    if metadata["greeks_path"]:
        logger.info("Loaded greeks CSV %s rows=%d", metadata["greeks_path"], metadata["greeks_rows"])

    return CsvLoadResult(positions=positions, quotes=quotes, metadata=metadata)


def _load_latest(base_dir: Path | str, pattern: str) -> pd.DataFrame:
    directory = _coerce_path(base_dir)
    if not directory.exists():
        return pd.DataFrame()
    latest = _latest_file(directory, pattern)
    if latest is None:
        return pd.DataFrame()
    return pd.read_csv(latest)


def _latest_file(directory: Path, pattern: str) -> Path | None:
    matches = list(directory.glob(pattern))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _coerce_path(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _read_csv(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except FileNotFoundError:
        return pd.DataFrame()


def _normalize_positions(positions_df: pd.DataFrame, greeks_df: pd.DataFrame) -> list[dict[str, Any]]:
    if positions_df is None or positions_df.empty:
        return []

    df = positions_df.copy()
    df.columns = [str(col).strip().lower() for col in df.columns]

    greeks_map: dict[str, dict[str, Any]] = {}
    if greeks_df is not None and not greeks_df.empty:
        gdf = greeks_df.copy()
        gdf.columns = [str(col).strip().lower() for col in gdf.columns]
        for row in gdf.to_dict("records"):
            symbol = str(row.get("symbol") or "").strip()
            if symbol:
                greeks_map[symbol] = {
                    key: row.get(key)
                    for key in ("delta", "gamma", "theta", "vega")
                    if row.get(key) is not None
                }

    records: list[dict[str, Any]] = []
    for row in df.to_dict("records"):
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        quantity = row.get("quantity", row.get("qty", row.get("position")))
        if quantity in (None, ""):
            quantity = 0
        avg_cost = row.get("avg_cost", row.get("average_cost", row.get("avgcost")))
        if avg_cost in (None, ""):
            avg_cost = 0
        entry: dict[str, Any] = {
            "symbol": symbol,
            "instrument_type": _normalize_type(row.get("type")),
            "quantity": quantity,
            "avg_cost": avg_cost,
            "multiplier": row.get("multiplier", 1),
            "account": row.get("account"),
            "previous_close": row.get("previous_close", row.get("prior_close", row.get("prev_close"))),
        }
        if entry["instrument_type"] == "option":
            entry.update(
                {
                    "underlying": row.get("underlying"),
                    "expiry": row.get("expiry", row.get("expiration")),
                    "right": row.get("right", row.get("call_put")),
                    "strike": row.get("strike"),
                    "ratio": row.get("ratio", row.get("ratio_quantity")),
                }
            )
        greeks = greeks_map.get(symbol)
        if greeks:
            entry.update(greeks)
        records.append(entry)

    return records


def _normalize_quotes(quotes_df: pd.DataFrame) -> list[dict[str, Any]]:
    if quotes_df is None or quotes_df.empty:
        return []

    df = quotes_df.copy()
    df.columns = [str(col).strip().lower() for col in df.columns]

    records: list[dict[str, Any]] = []
    for row in df.to_dict("records"):
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        records.append(
            {
                "symbol": symbol,
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "last": row.get("last", row.get("close")),
                "previous_close": row.get("previous_close", row.get("prior_close", row.get("prev_close"))),
                "session": row.get("session"),
                "timestamp": row.get("ts"),
            }
        )
    return records


def _normalize_type(value: Any) -> str:
    if value is None:
        return "equity"
    text = str(value).strip().lower()
    if text.startswith("option"):
        return "option"
    return "equity"
