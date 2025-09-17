# SPDX-License-Identifier: MIT

"""CSV ingestion helpers for live portfolio artifacts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_POSITIONS_PATTERN = "live_positions_*.csv"
_QUOTES_PATTERN = "live_quotes_*.csv"
_GREEKS_FILE = "portfolio_greeks_totals.csv"


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
