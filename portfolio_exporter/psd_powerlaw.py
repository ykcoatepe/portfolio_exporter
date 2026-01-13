from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger("portfolio_exporter.psd_powerlaw")

TZ_NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class PowerlawConfig:
    repo_root: Path | None
    output_dir: Path | None
    refresh_enabled: bool
    stale_trading_days: int
    refresh_timeout_sec: int
    refresh_cooldown_sec: int
    refresh_cmd: tuple[str, ...] | None


@dataclass
class RefreshState:
    in_flight: bool = False
    last_attempt: float | None = None
    last_status: str | None = None
    last_error: str | None = None


_REFRESH_STATE = RefreshState()
_REFRESH_LOCK = threading.Lock()
_TRADING_DAYS_CACHE: dict[tuple[date, int], list[date]] = {}
_TRADING_DAYS_LOCK = threading.Lock()


def load_powerlaw_snapshot(now: datetime | None = None) -> dict[str, Any] | None:
    cfg = _load_config()
    if cfg.output_dir is None:
        return {
            "stale": True,
            "stale_reason": "config_missing",
            "refresh": {"enabled": False, "status": "disabled"},
        }

    snapshot_path = _select_latest_snapshot(cfg.output_dir)
    raw: dict[str, Any] | None = None
    if snapshot_path is not None:
        raw = _load_json(snapshot_path)

    normalized = _normalize_snapshot(raw)
    as_of = _parse_date(normalized.get("as_of")) if normalized else None

    stale, stale_reason = _is_stale(as_of, now, cfg.stale_trading_days)
    if raw is None:
        stale = True
        stale_reason = "missing_snapshot"

    _maybe_start_refresh(stale, cfg)
    refresh_meta = _refresh_payload(cfg)

    payload = dict(normalized)
    if not payload.get("data_quality"):
        payload["data_quality"] = "WARN" if stale else "OK"
    payload.update(
        {
            "stale": stale,
            "stale_reason": stale_reason,
            "refresh": refresh_meta,
        }
    )
    if as_of:
        payload["as_of"] = as_of.isoformat()
    return payload


def request_powerlaw_refresh(force: bool = False) -> dict[str, Any]:
    cfg = _load_config()
    if cfg.output_dir is None and cfg.refresh_cmd is None:
        return {
            "started": False,
            "status": "disabled",
            "reason": "config_missing",
            "refresh": _refresh_payload(cfg),
        }
    if cfg.repo_root is None and cfg.refresh_cmd is None:
        return {
            "started": False,
            "status": "disabled",
            "reason": "config_missing",
            "refresh": _refresh_payload(cfg),
        }
    return _start_refresh(cfg, force=force)


def _load_config() -> PowerlawConfig:
    repo_env = os.getenv("PSD_POWERLAW_REPO", "").strip()
    repo_root = Path(repo_env).expanduser() if repo_env else _default_repo_root()
    if repo_root and not repo_root.exists():
        repo_root = None

    output_env = os.getenv("PSD_POWERLAW_OUTPUT_DIR", "output").strip()
    output_dir = None
    if output_env:
        candidate = Path(output_env).expanduser()
        if candidate.is_absolute():
            output_dir = candidate
        elif repo_root:
            output_dir = repo_root / candidate

    refresh_enabled = _parse_bool(os.getenv("PSD_POWERLAW_REFRESH", "1"))
    stale_days = _parse_int(os.getenv("PSD_POWERLAW_STALE_TRADING_DAYS", "1"), 1)
    timeout_sec = _parse_int(os.getenv("PSD_POWERLAW_REFRESH_TIMEOUT_SEC", "300"), 300)
    cooldown_sec = _parse_int(
        os.getenv("PSD_POWERLAW_REFRESH_COOLDOWN_SEC", "900"), 900
    )

    refresh_cmd = os.getenv("PSD_POWERLAW_CMD", "").strip() or None
    refresh_cmd_tokens = tuple(shlex.split(refresh_cmd)) if refresh_cmd else None

    return PowerlawConfig(
        repo_root=repo_root,
        output_dir=output_dir,
        refresh_enabled=refresh_enabled,
        stale_trading_days=stale_days,
        refresh_timeout_sec=timeout_sec,
        refresh_cooldown_sec=cooldown_sec,
        refresh_cmd=refresh_cmd_tokens,
    )


def _default_repo_root() -> Path | None:
    repo_root = Path(__file__).resolve().parents[1]
    candidate = repo_root.parent / "codeforge-powerlaw-trader"
    return candidate if candidate.exists() else None


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_int(raw: str, default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(value, 1)


def _select_latest_snapshot(output_dir: Path) -> Path | None:
    if not output_dir.exists():
        return None
    candidates = list(output_dir.glob("trader_v5_daily_*.json"))
    if not candidates:
        return None
    by_date: list[tuple[date, Path]] = []
    for path in candidates:
        candidate_date = _parse_date(_parse_date_from_name(path.name))
        if candidate_date:
            by_date.append((candidate_date, path))
    if by_date:
        by_date.sort(key=lambda item: item[0])
        return by_date[-1][1]
    candidates.sort(key=lambda p: p.stat().st_mtime)
    return candidates[-1]


def _parse_date_from_name(name: str) -> str | None:
    parts = name.replace("trader_v5_daily_", "").replace(".json", "")
    if len(parts) == 10 and parts[4] == "-" and parts[7] == "-":
        return parts
    return None


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("powerlaw snapshot load failed: %s", exc)
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_snapshot(raw: dict[str, Any] | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if not raw:
        return {}
    equity_weights = _coerce_mapping(raw.get("equity_weights"))
    hedge_notional = _coerce_mapping(raw.get("hedge_notional"))
    raw_small_cap = raw.get("small_cap")
    if isinstance(raw_small_cap, dict):
        small_cap_raw: dict[str, Any] = raw_small_cap
    else:
        small_cap_raw = {}
    small_cap = {
        "theta_pct_nav": _coerce_float(small_cap_raw.get("theta_pct_nav")),
        "can_open_new_trades": _coerce_bool(small_cap_raw.get("can_open_new_trades")),
        "plke_band": _coerce_str(small_cap_raw.get("plke_band")),
    }
    vutil_used = _coerce_float(raw.get("vutil_used"))
    if vutil_used is None:
        vutil_used = _coerce_float(raw.get("v_vega_utilization"))

    plke_band = _coerce_str(raw.get("plke_band_alpha"))
    if plke_band is None:
        plke_band = _coerce_str(raw.get("plke_band_aplh"))

    data_quality_detail = _coerce_str_list(raw.get("data_quality_detail"))
    if not data_quality_detail:
        data_quality_detail = _coerce_str_list(raw.get("data_warnings"))

    return {
        "as_of": _coerce_str(raw.get("as_of")),
        "plke": _coerce_float(raw.get("plke")),
        "plke_band_alpha": plke_band,
        "risk_state": _coerce_str(raw.get("risk_state")),
        "vol_bucket": _coerce_str(raw.get("vol_bucket")),
        "vutil_used": vutil_used,
        "vutil_source": _coerce_str(raw.get("vutil_source")),
        "vix_spot": _coerce_float(raw.get("vix_spot")),
        "vvix_spot": _coerce_float(raw.get("vvix_spot")),
        "vx_backwardation": _coerce_bool(raw.get("vx_backwardation")),
        "equity_weights": equity_weights,
        "hedge_notional": hedge_notional,
        "small_cap": small_cap,
        "data_quality": _coerce_str(raw.get("data_quality")),
        "data_quality_detail": data_quality_detail,
    }


def _coerce_mapping(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for key, raw_val in value.items():
        number = _coerce_float(raw_val)
        if number is None:
            continue
        out[str(key)] = number
    return out


def _coerce_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN guard
        return None
    return number


def _coerce_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return None


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        out = []
        for item in value:
            text = _coerce_str(item)
            if text:
                out.append(text)
        return out
    text = _coerce_str(value)
    return [text] if text else []


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed.date()


def _is_stale(
    as_of: date | None,
    now: datetime | None,
    stale_days: int,
) -> tuple[bool, str | None]:
    if as_of is None:
        return True, "missing_as_of"
    reference = now.astimezone(TZ_NY) if now else datetime.now(TZ_NY)
    threshold = _stale_threshold(reference.date(), stale_days)
    if as_of < threshold:
        return True, "behind_trading_day"
    return False, None


def _stale_threshold(reference: date, stale_days: int) -> date:
    stale_days = max(stale_days, 1)
    # Treat stale_days as the allowed trading-day lag (1 => yesterday is still fresh).
    allowed_window = stale_days + 1
    trading_days = _calendar_trading_days(
        reference, lookback=max(20, allowed_window * 5)
    )
    if trading_days:
        idx = -min(allowed_window, len(trading_days))
        return trading_days[idx]
    return _fallback_trading_day(reference, allowed_window)


def _calendar_trading_days(reference: date, lookback: int) -> list[date]:
    cache_key = (reference, lookback)
    with _TRADING_DAYS_LOCK:
        cached = _TRADING_DAYS_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)

    start = reference - timedelta(days=lookback)
    try:
        import exchange_calendars as xc
    except Exception:
        xc = None
    if xc is not None:
        try:
            nyse = xc.get_calendar("XNYS")
            schedule = nyse.schedule(start, reference)
        except Exception:
            schedule = None
        if schedule is not None and not schedule.empty:
            days = [ts.date() for ts in schedule["market_open"].dt.tz_convert(TZ_NY)]
            with _TRADING_DAYS_LOCK:
                _TRADING_DAYS_CACHE[cache_key] = days
            return days

    try:
        import pandas_market_calendars as pmc
    except Exception:
        pmc = None
    if pmc is not None:
        try:
            nyse = pmc.get_calendar("XNYS")
            schedule = nyse.schedule(start_date=start, end_date=reference)
        except Exception:
            schedule = None
        if schedule is not None and not schedule.empty:
            days = [ts.date() for ts in schedule["market_open"].dt.tz_convert(TZ_NY)]
            with _TRADING_DAYS_LOCK:
                _TRADING_DAYS_CACHE[cache_key] = days
            return days

    days = _fallback_trading_days(start, reference)
    with _TRADING_DAYS_LOCK:
        _TRADING_DAYS_CACHE[cache_key] = days
    return days


def _fallback_trading_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _fallback_trading_day(reference: date, stale_days: int) -> date:
    remaining = stale_days
    current = reference
    while remaining > 0:
        if current.weekday() < 5:
            remaining -= 1
            if remaining == 0:
                return current
        current -= timedelta(days=1)
    return reference


def _maybe_start_refresh(stale: bool, cfg: PowerlawConfig) -> None:
    if not stale or not cfg.refresh_enabled:
        return
    if cfg.repo_root is None and cfg.refresh_cmd is None:
        return
    _start_refresh(cfg, force=False)


def _start_refresh(cfg: PowerlawConfig, force: bool) -> dict[str, Any]:
    now = time.time()
    thread: threading.Thread | None = None
    started = False
    status = "idle"
    reason: str | None = None
    with _REFRESH_LOCK:
        if _REFRESH_STATE.in_flight:
            started = False
            status = "running"
            reason = "in_flight"
        else:
            last_attempt = _REFRESH_STATE.last_attempt or 0.0
            if not force and now - last_attempt < cfg.refresh_cooldown_sec:
                started = False
                status = _REFRESH_STATE.last_status or "cooldown"
                reason = "cooldown"
            else:
                _REFRESH_STATE.in_flight = True
                _REFRESH_STATE.last_attempt = now
                _REFRESH_STATE.last_status = "running"
                _REFRESH_STATE.last_error = None
                started = True
                status = "running"
                reason = None
                thread = threading.Thread(
                    target=_run_refresh,
                    name="psd-powerlaw-refresh",
                    args=(cfg,),
                    daemon=True,
                )

    if thread is not None:
        thread.start()

    return {
        "started": started,
        "status": status,
        "reason": reason,
        "refresh": _refresh_payload(cfg),
    }


def _run_refresh(cfg: PowerlawConfig) -> None:
    status = "failed"
    error = None
    try:
        cmd = _build_refresh_cmd(cfg)
        result = subprocess.run(
            cmd,
            cwd=cfg.repo_root,
            timeout=cfg.refresh_timeout_sec,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            status = "success"
        else:
            status = "failed"
            error = f"exit {result.returncode}"
    except subprocess.TimeoutExpired:
        status = "timeout"
        error = f"timeout after {cfg.refresh_timeout_sec}s"
    except Exception as exc:  # pragma: no cover - defensive
        status = "failed"
        error = str(exc)

    with _REFRESH_LOCK:
        _REFRESH_STATE.in_flight = False
        _REFRESH_STATE.last_status = status
        _REFRESH_STATE.last_error = error

    if status == "success":
        logger.info("powerlaw refresh succeeded")
    else:
        logger.warning("powerlaw refresh failed (%s)", error or status)


def _build_refresh_cmd(cfg: PowerlawConfig) -> list[str]:
    if cfg.refresh_cmd:
        return list(cfg.refresh_cmd)
    if cfg.repo_root is None:
        raise ValueError("Powerlaw repo root not configured")
    output_dir = cfg.output_dir
    if output_dir is None:
        raise ValueError("Powerlaw output directory not configured")
    script_path = cfg.repo_root / "scripts" / "run_trader_v5_daily.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Missing Powerlaw refresh script: {script_path}")
    python_path = _select_repo_python(cfg.repo_root)
    return [
        str(python_path),
        str(script_path),
        "--refresh-prices",
        "--refresh-vx",
        "--no-input",
        "--no-orders",
        "--allow-warn",
        "--output-dir",
        str(output_dir),
    ]


def _select_repo_python(repo_root: Path) -> Path:
    candidates = (
        repo_root / "venv" / "bin" / "python",
        repo_root / ".venv" / "bin" / "python",
        repo_root / "venv" / "Scripts" / "python.exe",
        repo_root / ".venv" / "Scripts" / "python.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return Path(sys.executable)


def _refresh_payload(cfg: PowerlawConfig) -> dict[str, Any]:
    with _REFRESH_LOCK:
        in_flight = _REFRESH_STATE.in_flight
        last_attempt = _REFRESH_STATE.last_attempt
        last_status = _REFRESH_STATE.last_status
        last_error = _REFRESH_STATE.last_error

    enabled = bool(
        cfg.refresh_enabled
        and (cfg.repo_root or cfg.refresh_cmd)
        and (cfg.output_dir or cfg.refresh_cmd)
    )
    status = "running" if in_flight else (last_status or "idle")
    if not enabled:
        status = "disabled"
    last_attempt_iso = (
        datetime.fromtimestamp(last_attempt, TZ_NY).isoformat()
        if last_attempt
        else None
    )
    return {
        "enabled": enabled,
        "status": status,
        "last_attempt": last_attempt_iso,
        "last_error": last_error,
    }
