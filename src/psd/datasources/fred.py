"""FRED datasource helpers for the Market Stress Barometer."""

from __future__ import annotations

import csv
import logging
import math
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import requests

from . import is_offline

logger = logging.getLogger("psd.datasource.fred")

_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_SERIES_ID = "BAMLH0A0HYM2"  # ICE BofA US High Yield Index Option-Adjusted Spread
_DEFAULT_START = "2000-01-01"


class _FredError(RuntimeError):
    """Internal marker for recoverable FRED failures."""


def _normalize_value(raw: str | float | int | None) -> str:
    if raw in (None, "", "."):
        return ""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return ""
    if math.isnan(value):
        return ""
    formatted = f"{value:.6f}".rstrip("0").rstrip(".")
    return formatted or "0"


def _load_existing(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return {
                str(row.get("date")): str(row.get("value", ""))
                for row in reader
                if row.get("date")
            }
    except Exception:  # pragma: no cover - best-effort cache read
        return {}


def _write_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "value"])
        writer.writerows(rows)
    tmp_path.replace(path)


def _should_retry(status_code: int, payload: Any) -> bool:
    if status_code == 429:
        return True
    if status_code >= 500:
        return True
    if isinstance(payload, dict) and payload.get("error_code") == 429:
        return True
    return False


def refresh_hy_csv(
    target: Path | str,
    *,
    env: Mapping[str, str] | None = None,
    api_key: str | None = None,
    session: requests.Session | None = None,
    series_id: str | None = None,
    max_retries: int = 4,
    backoff_seconds: float = 1.5,
) -> bool:
    """Update ``target`` with the latest HY-OAS observations from FRED.

    Returns ``True`` when the CSV was rewritten with fresh data. When the
    environment is configured for offline/test execution or no API key is
    available, the helper skips network IO and returns ``False`` gracefully.
    """

    env_map = env or os.environ
    if is_offline(env_map):
        logger.debug("FRED refresh skipped: offline mode detected")
        return False

    api_key = api_key or env_map.get("FRED_API_KEY")
    if not api_key:
        logger.debug("FRED refresh skipped: FRED_API_KEY not set")
        return False

    target_path = Path(target)
    existing = _load_existing(target_path)
    if existing:
        last_date = max(existing)
        observation_start = last_date
    else:
        observation_start = env_map.get("MSB_FRED_START", _DEFAULT_START)

    params = {
        "series_id": series_id or env_map.get("MSB_FRED_SERIES", DEFAULT_SERIES_ID),
        "api_key": api_key,
        "file_type": "json",
        "observation_start": observation_start,
        "sort_order": "asc",
    }

    sess = session or requests.Session()
    close_session = session is None
    attempt = 0
    backoff = max(backoff_seconds, 0.5)
    payload: dict[str, Any] | None = None
    try:
        while attempt < max_retries:
            attempt += 1
            try:
                response = sess.get(_BASE_URL, params=params, timeout=15)
            except requests.RequestException as exc:  # pragma: no cover - network edge
                logger.warning("FRED request failed (attempt %s): %s", attempt, exc)
                if attempt >= max_retries:
                    raise _FredError("network error") from exc
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)
                continue

            status = response.status_code
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if _should_retry(status, payload):
                logger.warning(
                    "FRED rate-limit/backoff (status=%s, attempt=%s)", status, attempt
                )
                if attempt >= max_retries:
                    raise _FredError(f"FRED request failed with status {status}")
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)
                continue
            if status >= 400:
                raise _FredError(f"FRED request failed ({status})")
            break
        else:  # pragma: no cover - defensive loop guard
            raise _FredError("FRED request exceeded retry budget")

        if not isinstance(payload, dict):
            raise _FredError("Unexpected FRED payload")

        observations = payload.get("observations")
        if not isinstance(observations, list):
            raise _FredError("FRED payload missing observations")

        merged = dict(existing)
        for item in observations:
            if not isinstance(item, dict):
                continue
            date_str = item.get("date")
            value_str = _normalize_value(item.get("value"))
            if not date_str or not value_str:
                continue
            merged[str(date_str)] = value_str

        if merged == existing and target_path.exists():
            logger.debug("FRED refresh skipped: no new points")
            return False

        rows = sorted(merged.items())
        _write_csv(target_path, rows)
        logger.info("FRED HY-OAS series refreshed (%s rows)", len(rows))
        return True
    finally:
        if close_session:
            try:
                sess.close()
            except Exception:  # pragma: no cover - cleanup guard
                pass


__all__ = ["refresh_hy_csv", "DEFAULT_SERIES_ID"]
