"""Vendor CSV refresh helpers for MSB inputs."""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from . import is_offline, resolve_msb_source
from .fred import refresh_hy_csv

_LOG = logging.getLogger("psd.datasources.msb_vendor")
_TRUE = {"1", "true", "yes", "on"}
_DEFAULT_TTL_HOURS = 12
_DEFAULT_PERIOD = "5y"
_DEFAULT_VX1_TICKERS = ("^VIX",)
_DEFAULT_VX2_TICKERS = ("^VIX3M",)
_DEFAULT_SPX_TICKERS = ("^GSPC",)
_DEFAULT_IBKR_VX_ROOTS = ("VIX", "VX")
_DEFAULT_IBKR_VX_EXCHANGE = "CFE"
_DEFAULT_IBKR_VX_CURRENCY = "USD"
_DEFAULT_IBKR_VX_INDEX_EXCHANGE = "CBOE"
_DEFAULT_IBKR_VX_INDEX_CURRENCY = "USD"
_DEFAULT_IBKR_VX1_INDEX = "VIX"
_DEFAULT_IBKR_VX2_INDEX = "VIX3M"
_DEFAULT_IBKR_SPX_SYMBOL = "SPX"
_DEFAULT_IBKR_SPX_EXCHANGE = "CBOE"
_DEFAULT_IBKR_SPX_CURRENCY = "USD"
_DEFAULT_IBKR_BAR_SIZE = "1 day"
_DEFAULT_IBKR_WHAT = "TRADES"
_DEFAULT_IBKR_USE_RTH = False
_DEFAULT_MIN_VX_ROWS = 30


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


def _env_list(
    env_map: Mapping[str, str],
    key: str,
    default: tuple[str, ...],
) -> list[str]:
    raw = env_map.get(key)
    if raw is None:
        return [item for item in default if str(item).strip()]
    items = [item.strip() for item in str(raw).split(",") if item.strip()]
    return items or [item for item in default if str(item).strip()]


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


def _parse_ib_duration(period: str) -> str:
    raw = str(period or "").strip()
    if not raw:
        return "5 Y"
    if " " in raw and raw.split()[0].isdigit():
        return raw
    match = re.match(r"^(\d+)([a-zA-Z]+)$", raw)
    if not match:
        return "5 Y"
    value = int(match.group(1))
    unit = match.group(2).lower()
    if unit in {"y", "yr", "yrs", "year", "years"}:
        return f"{value} Y"
    if unit in {"m", "mo", "mon", "month", "months"}:
        return f"{value} M"
    if unit in {"w", "wk", "week", "weeks"}:
        return f"{value} W"
    if unit in {"d", "day", "days"}:
        return f"{value} D"
    return "5 Y"


def _parse_future_expiry(raw: str | None) -> datetime:
    if not raw:
        return datetime(1900, 1, 1)
    token = str(raw).strip().replace("-", "").replace("/", "")
    for fmt, length in (("%Y%m%d", 8), ("%Y%m", 6)):
        try:
            return datetime.strptime(token[:length], fmt)
        except ValueError:
            continue
    return datetime(1900, 1, 1)


def _bars_to_series(bars: list[Any]) -> pd.Series:
    if not bars:
        return pd.Series(dtype=float)
    dates = []
    values = []
    for bar in bars:
        try:
            dt = pd.to_datetime(getattr(bar, "date", None))
        except Exception:
            continue
        try:
            close_val = float(getattr(bar, "close", None))
        except Exception:
            continue
        dates.append(dt)
        values.append(close_val)
    if not dates:
        return pd.Series(dtype=float)
    series = pd.Series(values, index=pd.to_datetime(dates)).sort_index()
    series = series[~series.index.duplicated(keep="last")]
    return series.dropna()


def _connect_ibkr(env_map: Mapping[str, str]) -> Any | None:
    try:
        from ib_insync import IB  # type: ignore

        from portfolio_exporter.core.ib_config import client_id, connect_ib
    except Exception as exc:  # pragma: no cover - optional deps/runtime
        _LOG.warning("IBKR client unavailable: %s", exc)
        return None
    ib = IB()
    try:
        port: int | None = None
        if env_map.get("IB_PORT"):
            try:
                port = int(str(env_map.get("IB_PORT")))
            except (TypeError, ValueError):
                port = None
        connect_ib(
            ib,
            host=env_map.get("IB_HOST"),
            port=port,
            client_id=client_id("msb_vendor", default=72),
            timeout=5,
        )
    except Exception as exc:  # pragma: no cover - runtime/network
        _LOG.warning("IBKR connection failed: %s", exc)
        try:
            ib.disconnect()
        except Exception:
            pass
        return None
    return ib


def _disconnect_ibkr(ib: Any | None) -> None:
    if ib is None:
        return
    try:
        if hasattr(ib, "isConnected") and ib.isConnected():
            ib.disconnect()
    except Exception:
        pass


def _download_close_series_ibkr_future(
    ib: Any,
    *,
    root: str,
    exchange: str,
    currency: str,
    position: int,
    duration: str,
    bar_size: str,
    what_to_show: str,
    use_rth: bool,
) -> pd.Series:
    try:
        from ib_insync import Future  # type: ignore
    except Exception as exc:  # pragma: no cover - optional deps
        raise RuntimeError("ib_insync not available") from exc
    details = ib.reqContractDetails(Future(root, exchange=exchange, currency=currency))
    if not details:
        return pd.Series(dtype=float)
    today = datetime.utcnow()
    contracts = []
    for detail in details:
        expiry = _parse_future_expiry(detail.contract.lastTradeDateOrContractMonth)
        if expiry >= today:
            contracts.append((expiry, detail.contract))
    contracts.sort(key=lambda item: item[0])
    if len(contracts) <= position:
        return pd.Series(dtype=float)
    contract = contracts[position][1]
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow=what_to_show,
        useRTH=use_rth,
        formatDate=1,
    )
    return _bars_to_series(bars)


def _download_close_series_ibkr_index(
    ib: Any,
    *,
    symbol: str,
    exchange: str,
    currency: str,
    duration: str,
    bar_size: str,
    what_to_show: str,
    use_rth: bool,
) -> pd.Series:
    try:
        from ib_insync import Index  # type: ignore
    except Exception as exc:  # pragma: no cover - optional deps
        raise RuntimeError("ib_insync not available") from exc
    contract = Index(symbol=symbol, exchange=exchange, currency=currency)
    details = ib.reqContractDetails(contract)
    if details:
        contract = details[0].contract
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow=what_to_show,
        useRTH=use_rth,
        formatDate=1,
    )
    return _bars_to_series(bars)


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

    msb_source = resolve_msb_source(env_map)

    hy_path = vendor_dir / "hy.csv"
    if msb_source in {"fred", "ibkr"} and env_map.get("FRED_API_KEY"):
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

    vx1_override = str(env_map.get("MSB_VX1_TICKER", "")).strip()
    vx2_override = str(env_map.get("MSB_VX2_TICKER", "")).strip()
    vx1_tickers = [vx1_override] if vx1_override else _env_list(
        env_map, "MSB_VX1_TICKERS", _DEFAULT_VX1_TICKERS
    )
    vx2_tickers = [vx2_override] if vx2_override else _env_list(
        env_map, "MSB_VX2_TICKERS", _DEFAULT_VX2_TICKERS
    )

    ib_client = _connect_ibkr(env_map) if msb_source == "ibkr" else None
    ib_duration = env_map.get("MSB_IBKR_DURATION") or _parse_ib_duration(period)
    ib_bar_size = str(env_map.get("MSB_IBKR_BAR_SIZE", _DEFAULT_IBKR_BAR_SIZE)).strip()
    ib_what = str(env_map.get("MSB_IBKR_WHAT", _DEFAULT_IBKR_WHAT)).strip()
    ib_use_rth = _env_flag(env_map, "MSB_IBKR_USE_RTH", _DEFAULT_IBKR_USE_RTH)

    vx_root_override = str(env_map.get("MSB_IBKR_VX_ROOT", "")).strip()
    vx_roots = [vx_root_override] if vx_root_override else _env_list(
        env_map, "MSB_IBKR_VX_ROOTS", _DEFAULT_IBKR_VX_ROOTS
    )
    vx_exchange = str(
        env_map.get("MSB_IBKR_VX_EXCHANGE", _DEFAULT_IBKR_VX_EXCHANGE)
    ).strip()
    vx_currency = str(
        env_map.get("MSB_IBKR_VX_CURRENCY", _DEFAULT_IBKR_VX_CURRENCY)
    ).strip()
    vx_index_exchange = str(
        env_map.get("MSB_IBKR_VX_INDEX_EXCHANGE", _DEFAULT_IBKR_VX_INDEX_EXCHANGE)
    ).strip()
    vx_index_currency = str(
        env_map.get("MSB_IBKR_VX_INDEX_CURRENCY", _DEFAULT_IBKR_VX_INDEX_CURRENCY)
    ).strip()
    vx1_index = str(env_map.get("MSB_IBKR_VX1_INDEX", _DEFAULT_IBKR_VX1_INDEX)).strip()
    vx2_index = str(env_map.get("MSB_IBKR_VX2_INDEX", _DEFAULT_IBKR_VX2_INDEX)).strip()
    min_vx_rows = _env_int(env_map, "MSB_MIN_VX_ROWS", _DEFAULT_MIN_VX_ROWS)

    spx_symbol = str(
        env_map.get("MSB_IBKR_SPX_SYMBOL", _DEFAULT_IBKR_SPX_SYMBOL)
    ).strip()
    spx_exchange = str(
        env_map.get("MSB_IBKR_SPX_EXCHANGE", _DEFAULT_IBKR_SPX_EXCHANGE)
    ).strip()
    spx_currency = str(
        env_map.get("MSB_IBKR_SPX_CURRENCY", _DEFAULT_IBKR_SPX_CURRENCY)
    ).strip()

    vx1_path = vendor_dir / "vx1.csv"
    if vx1_tickers:
        if _should_refresh(vx1_path, ttl_hours, force):
            series = pd.Series(dtype=float)
            if ib_client and vx_roots:
                for root in vx_roots:
                    if not root:
                        continue
                    try:
                        series = _download_close_series_ibkr_future(
                            ib_client,
                            root=root,
                            exchange=vx_exchange,
                            currency=vx_currency,
                            position=0,
                            duration=ib_duration,
                            bar_size=ib_bar_size,
                            what_to_show=ib_what,
                            use_rth=ib_use_rth,
                        )
                    except Exception as exc:  # pragma: no cover - runtime/network
                        _LOG.warning("IBKR VX1 refresh failed: %s", exc)
                        series = pd.Series(dtype=float)
                    if not series.empty:
                        break
            if ib_client and (series.empty or len(series) < min_vx_rows):
                if vx1_index:
                    try:
                        series = _download_close_series_ibkr_index(
                            ib_client,
                            symbol=vx1_index,
                            exchange=vx_index_exchange,
                            currency=vx_index_currency,
                            duration=ib_duration,
                            bar_size=ib_bar_size,
                            what_to_show=ib_what,
                            use_rth=ib_use_rth,
                        )
                    except Exception as exc:  # pragma: no cover - runtime/network
                        _LOG.warning("IBKR VX1 index refresh failed: %s", exc)
                        series = pd.Series(dtype=float)
            if series.empty:
                for ticker in vx1_tickers:
                    if not ticker:
                        continue
                    try:
                        series = _download_close_series_yf(ticker, period)
                    except Exception as exc:  # pragma: no cover - depends on network/env
                        _LOG.warning("VX1 refresh failed: %s", exc)
                        status["vx1"] = "error"
                        series = pd.Series(dtype=float)
                    if not series.empty:
                        break
            if series.empty:
                status["vx1"] = "empty"
            else:
                _write_series(series, vx1_path)
                status["vx1"] = "refreshed"
        else:
            status["vx1"] = "fresh"
    else:
        status["vx1"] = "disabled"

    vx2_path = vendor_dir / "vx2.csv"
    if vx2_tickers:
        if _should_refresh(vx2_path, ttl_hours, force):
            series = pd.Series(dtype=float)
            if ib_client and vx_roots:
                for root in vx_roots:
                    if not root:
                        continue
                    try:
                        series = _download_close_series_ibkr_future(
                            ib_client,
                            root=root,
                            exchange=vx_exchange,
                            currency=vx_currency,
                            position=1,
                            duration=ib_duration,
                            bar_size=ib_bar_size,
                            what_to_show=ib_what,
                            use_rth=ib_use_rth,
                        )
                    except Exception as exc:  # pragma: no cover - runtime/network
                        _LOG.warning("IBKR VX2 refresh failed: %s", exc)
                        series = pd.Series(dtype=float)
                    if not series.empty:
                        break
            if ib_client and (series.empty or len(series) < min_vx_rows):
                if vx2_index:
                    try:
                        series = _download_close_series_ibkr_index(
                            ib_client,
                            symbol=vx2_index,
                            exchange=vx_index_exchange,
                            currency=vx_index_currency,
                            duration=ib_duration,
                            bar_size=ib_bar_size,
                            what_to_show=ib_what,
                            use_rth=ib_use_rth,
                        )
                    except Exception as exc:  # pragma: no cover - runtime/network
                        _LOG.warning("IBKR VX2 index refresh failed: %s", exc)
                        series = pd.Series(dtype=float)
            if series.empty:
                for ticker in vx2_tickers:
                    if not ticker:
                        continue
                    try:
                        series = _download_close_series_yf(ticker, period)
                    except Exception as exc:  # pragma: no cover - depends on network/env
                        _LOG.warning("VX2 refresh failed: %s", exc)
                        status["vx2"] = "error"
                        series = pd.Series(dtype=float)
                    if not series.empty:
                        break
            if series.empty:
                status["vx2"] = "empty"
            else:
                _write_series(series, vx2_path)
                status["vx2"] = "refreshed"
        else:
            status["vx2"] = "fresh"
    else:
        status["vx2"] = "disabled"

    spx_override = str(env_map.get("MSB_SPX_TICKER", "")).strip()
    spx_tickers = [spx_override] if spx_override else _env_list(
        env_map, "MSB_SPX_TICKERS", _DEFAULT_SPX_TICKERS
    )
    spx_path = vendor_dir / "spx_ret.csv"
    if spx_tickers:
        if _should_refresh(spx_path, ttl_hours, force):
            series = pd.Series(dtype=float)
            if ib_client and spx_symbol:
                try:
                    series = _download_close_series_ibkr_index(
                        ib_client,
                        symbol=spx_symbol,
                        exchange=spx_exchange,
                        currency=spx_currency,
                        duration=ib_duration,
                        bar_size=ib_bar_size,
                        what_to_show=ib_what,
                        use_rth=ib_use_rth,
                    )
                except Exception as exc:  # pragma: no cover - runtime/network
                    _LOG.warning("IBKR SPX refresh failed: %s", exc)
            if series.empty:
                for ticker in spx_tickers:
                    if not ticker:
                        continue
                    try:
                        series = _download_close_series_yf(ticker, period)
                    except Exception as exc:  # pragma: no cover - depends on network/env
                        _LOG.warning("SPX return refresh failed: %s", exc)
                        status["spx_ret"] = "error"
                        series = pd.Series(dtype=float)
                    if not series.empty:
                        break
            returns = series.pct_change().dropna() if not series.empty else series
            if returns.empty:
                status["spx_ret"] = "empty"
            else:
                _write_series(returns, spx_path)
                status["spx_ret"] = "refreshed"
        else:
            status["spx_ret"] = "fresh"
    else:
        status["spx_ret"] = "disabled"

    _disconnect_ibkr(ib_client)

    return status
