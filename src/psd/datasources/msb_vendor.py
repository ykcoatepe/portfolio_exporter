"""Vendor CSV refresh helpers for MSB inputs."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from . import is_offline, resolve_msb_source
from .fred import refresh_hy_csv

_LOG = logging.getLogger("psd.datasources.msb_vendor")
_TRUE = {"1", "true", "yes", "on"}
_DEFAULT_TTL_HOURS = 12
_DEFAULT_PERIOD = "5y"
_DEFAULT_VX1_TICKER = "VX=F"
_DEFAULT_VX2_TICKER = "VXF=F"
_DEFAULT_SPX_TICKER = "^GSPC"


def _env_flag(env_map: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env_map.get(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in _TRUE


def _env_int(env_map: Mapping[str, str], key: str, default: int) -> int:
    raw = env_map.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _should_refresh(path: Path, ttl_hours: int, force: bool) -> bool:
    if force:
        return True
    if not path.exists():
        return True
    if ttl_hours <= 0:
        return True
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return True
    return age >= ttl_hours * 3600


def _write_series(series: pd.Series, path: Path) -> None:
    if series.empty:
        raise ValueError("series is empty")
    frame = pd.DataFrame({"date": series.index, "value": series.values})
    frame["date"] = pd.to_datetime(frame["date"]).dt.date.astype(str)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _download_close_series_yf(ticker: str, period: str) -> pd.Series:
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional deps
        raise RuntimeError("yfinance not available") from exc

    df = yf.download(
        tickers=ticker,
        period=period,
        interval="1d",
        progress=False,
        auto_adjust=False,
    )
    if df is None or len(df) == 0:
        return pd.Series(dtype=float)
    close = df.get("Close")
    if close is None:
        close = df.get("close")
    if close is None:
        return pd.Series(dtype=float)
    series = close.astype(float)
    series.index = pd.to_datetime(series.index)
    series = series[~series.index.duplicated(keep="last")].sort_index()
    return series.dropna()


def refresh_vendor_data(
    vendor_root: Path | str,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env_map = env or os.environ
    if is_offline(env_map):
        return {"skipped": "offline"}
    if not _env_flag(env_map, "PSD_MSB_AUTO_REFRESH", True):
        return {"skipped": "disabled"}

    vendor_dir = Path(vendor_root)
    vendor_dir.mkdir(parents=True, exist_ok=True)

    ttl_hours = _env_int(env_map, "MSB_VENDOR_TTL_HOURS", _DEFAULT_TTL_HOURS)
    force = _env_flag(env_map, "MSB_VENDOR_FORCE_REFRESH", False)
    period = (
        str(env_map.get("MSB_VENDOR_PERIOD", _DEFAULT_PERIOD)).strip()
        or _DEFAULT_PERIOD
    )

    status: dict[str, Any] = {}

    hy_path = vendor_dir / "hy.csv"
    if resolve_msb_source(env_map) == "fred":
        if _should_refresh(hy_path, ttl_hours, force):
            try:
                refreshed = refresh_hy_csv(hy_path, env=env_map)
            except Exception as exc:  # pragma: no cover - depends on network/env
                _LOG.warning("HY refresh failed: %s", exc)
                status["hy"] = "error"
            else:
                status["hy"] = "refreshed" if refreshed else "unchanged"
        else:
            status["hy"] = "fresh"
    elif not hy_path.exists():
        status["hy"] = "missing"

    vx1_ticker = str(env_map.get("MSB_VX1_TICKER", _DEFAULT_VX1_TICKER)).strip()
    vx2_ticker = str(env_map.get("MSB_VX2_TICKER", _DEFAULT_VX2_TICKER)).strip()

    vx1_path = vendor_dir / "vx1.csv"
    if vx1_ticker:
        if _should_refresh(vx1_path, ttl_hours, force):
            try:
                series = _download_close_series_yf(vx1_ticker, period)
                if series.empty:
                    status["vx1"] = "empty"
                else:
                    _write_series(series, vx1_path)
                    status["vx1"] = "refreshed"
            except Exception as exc:  # pragma: no cover - depends on network/env
                _LOG.warning("VX1 refresh failed: %s", exc)
                status["vx1"] = "error"
        else:
            status["vx1"] = "fresh"
    else:
        status["vx1"] = "disabled"

    vx2_path = vendor_dir / "vx2.csv"
    if vx2_ticker:
        if _should_refresh(vx2_path, ttl_hours, force):
            try:
                series = _download_close_series_yf(vx2_ticker, period)
                if series.empty:
                    status["vx2"] = "empty"
                else:
                    _write_series(series, vx2_path)
                    status["vx2"] = "refreshed"
            except Exception as exc:  # pragma: no cover - depends on network/env
                _LOG.warning("VX2 refresh failed: %s", exc)
                status["vx2"] = "error"
        else:
            status["vx2"] = "fresh"
    else:
        status["vx2"] = "disabled"

    spx_ticker = str(env_map.get("MSB_SPX_TICKER", _DEFAULT_SPX_TICKER)).strip()
    spx_path = vendor_dir / "spx_ret.csv"
    if spx_ticker:
        if _should_refresh(spx_path, ttl_hours, force):
            try:
                series = _download_close_series_yf(spx_ticker, period)
                returns = series.pct_change().dropna()
                if returns.empty:
                    status["spx_ret"] = "empty"
                else:
                    _write_series(returns, spx_path)
                    status["spx_ret"] = "refreshed"
            except Exception as exc:  # pragma: no cover - depends on network/env
                _LOG.warning("SPX return refresh failed: %s", exc)
                status["spx_ret"] = "error"
        else:
            status["spx_ret"] = "fresh"
    else:
        status["spx_ret"] = "disabled"

    return status
