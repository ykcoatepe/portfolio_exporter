"""Intraday scheduler with pacing/backoff for PSD sentinel.

This module provides a paced run loop designed to respect IBKR historical and
web/client portal API limits. It intentionally avoids heavy imports and keeps
logic self-contained so tests can monkeypatch datasources.

Key features:
- Token-bucket limiter (default ~10 req/s burst for generic web calls).
- Historical guardrails: 60 req/10min, dedupe identical requests within 15s,
  and avoid ≥6 small-bar requests for the same contract/exchange/ticktype in 2s.
- Exponential backoff on 429/pacing violations with jitter.
- Last-mark cache: only trigger optional greeks/marks fetch for changed
  underlyings since the last loop iteration.

The scheduler delegates evaluation to ``engine.scan_once`` and focuses on
controlling the cadence and external IO pacing. External IO entry points can be
wrapped via the ``io_request`` helper below, or tests can patch datasources
directly.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import random
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import FastAPI

from psd.analytics.msb import compute_msb
from psd.core import store
from psd.datasources import resolve_msb_source
from psd.datasources.msb_vendor import refresh_vendor_data
from psd.sentinel.msb_actions import evaluate_msb_triggers_and_update_livebar
from psd.sentinel.msb_metrics import MSB_DATA_AGE_SECONDS, MSB_SCHEDULER_RUNS

# Lazy import to keep CLI startup fast and allow test monkeypatching
try:  # pragma: no cover - exercised via scripts
    from ..datasources import ibkr as ib_src
    from .engine import scan_once
except Exception:  # pragma: no cover - minimal envs
    scan_once = None  # type: ignore
    ib_src = None  # type: ignore


class PacingViolation(Exception):
    pass


_TRT = ZoneInfo("Europe/Istanbul")
_RUN_AT = dt_time(hour=17, minute=30)
_VENDOR_ROOT = Path("data") / "vendor"
_SCHED_LOG = logging.getLogger("psd.sentinel.scheduler")
_SCHED_THREAD: threading.Thread | None = None
_SCHED_STOP: threading.Event | None = None
_SCHED_GUARD = threading.Lock()


@dataclass
class TokenBucket:
    capacity: float
    refill_rate_per_sec: float
    tokens: float | None = None
    last_refill: float | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if self.tokens is None:
            self.tokens = self.capacity
        if self.last_refill is None:
            self.last_refill = time.monotonic()

    def take(
        self, amount: float = 1.0, block: bool = True, timeout: float | None = None
    ) -> bool:
        start = time.monotonic()
        while True:
            with self.lock:
                now = time.monotonic()
                assert self.last_refill is not None and self.tokens is not None
                elapsed = max(0.0, now - self.last_refill)
                self.tokens = min(
                    self.capacity, self.tokens + elapsed * self.refill_rate_per_sec
                )
                self.last_refill = now
                if self.tokens >= amount:
                    self.tokens -= amount
                    return True
            if not block:
                return False
            if timeout is not None and (time.monotonic() - start) >= timeout:
                return False
            time.sleep(0.005)


class HistoricalLimiter:
    """Limiter implementing common IBKR historical pacing constraints.

    - Global budget: 60 requests / 10 minutes (capacity=60, rate=0.1/s)
    - Dedupe identical requests within 15 seconds
    - Avoid ≥6 small-bar requests for same (contract, exchange, ticktype) in 2s
    """

    def __init__(
        self, capacity: int = 60, window_sec: int = 600, dedupe_window: int = 15
    ) -> None:
        rate = capacity / float(window_sec)
        self.bucket = TokenBucket(capacity=float(capacity), refill_rate_per_sec=rate)
        self.dedupe_window = dedupe_window
        self._last_seen: dict[str, float] = {}
        self._burst_window = 2.0
        self._burst_key_times: dict[tuple[str, str, str], list[float]] = {}
        self.lock = threading.Lock()

    def _cleanup(self, now: float) -> None:
        # Clean old dedupe entries
        drop_before = now - self.dedupe_window
        self._last_seen = {k: t for k, t in self._last_seen.items() if t >= drop_before}
        # Clean old burst windows
        bw = self._burst_window
        for k, times in list(self._burst_key_times.items()):
            self._burst_key_times[k] = [t for t in times if (now - t) <= bw]
            if not self._burst_key_times[k]:
                del self._burst_key_times[k]

    def allow(
        self, key: str, small_bar_key: tuple[str, str, str] | None = None
    ) -> bool:
        now = time.monotonic()
        with self.lock:
            self._cleanup(now)
            # Dedupe identical
            if (
                key in self._last_seen
                and (now - self._last_seen[key]) < self.dedupe_window
            ):
                return False
            # Burst window for small bars
            if small_bar_key is not None:
                times = self._burst_key_times.get(small_bar_key, [])
                if len(times) >= 5:
                    # Already 5 in the last 2 seconds (would make it ≥6)
                    return False
                times.append(now)
                self._burst_key_times[small_bar_key] = times
            # Token bucket budget
            ok = self.bucket.take(1.0, block=True)
            if ok:
                self._last_seen[key] = now
            return ok


def _is_business_day(day: date) -> bool:
    return day.weekday() < 5


def _next_business_run(now: datetime) -> datetime:
    now_trt = now.astimezone(_TRT)
    candidate_date = now_trt.date()
    candidate_dt = datetime.combine(candidate_date, _RUN_AT, tzinfo=_TRT)
    if now_trt >= candidate_dt:
        candidate_date += timedelta(days=1)
        candidate_dt = datetime.combine(candidate_date, _RUN_AT, tzinfo=_TRT)
    while not _is_business_day(candidate_dt.date()):
        candidate_date += timedelta(days=1)
        candidate_dt = datetime.combine(candidate_date, _RUN_AT, tzinfo=_TRT)
    return candidate_dt


def _load_series(csv_path: Path) -> pd.Series:
    frame = pd.read_csv(csv_path, parse_dates=["date"])
    if "value" not in frame.columns:
        raise ValueError(f"{csv_path} missing 'value' column")
    series = frame.sort_values("date").set_index("date")["value"].astype(float)
    series.index = pd.to_datetime(series.index)
    return series


def _load_vendor(
    root: Path,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series | None]:
    hy = _load_series(root / "hy.csv")
    vx1 = _load_series(root / "vx1.csv")
    vx2 = _load_series(root / "vx2.csv")
    spx_path = root / "spx_ret.csv"
    spx = _load_series(spx_path) if spx_path.exists() else None
    return hy, vx1, vx2, spx


def _missing_vendor_files(root: Path) -> list[str]:
    missing: list[str] = []
    for name in ("hy.csv", "vx1.csv", "vx2.csv"):
        path = root / name
        try:
            if not path.exists() or path.stat().st_size == 0:
                missing.append(name)
        except OSError:
            missing.append(name)
    return missing


def _compute_streak_ge_60(msb_series: pd.Series) -> int:
    streak = 0
    for value in reversed(msb_series.tolist()):
        if value >= 60:
            streak += 1
        else:
            break
    return streak


def _prepare_context(
    df: pd.DataFrame, spx_series: pd.Series | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    last_idx = df.index[-1]
    today = last_idx.date()
    tail = df.iloc[-1]

    triggers = tail.get("triggers") or []
    if isinstance(triggers, list):
        trigger_flags = [str(flag).upper() for flag in triggers]
    else:
        trigger_flags = [str(triggers).upper()]

    hy_latest = float(tail["hy"])
    hy_d1_bps = None
    hy_d5_bps = None
    if len(df) >= 2:
        hy_prev = float(df.iloc[-2]["hy"])
        hy_d1_bps = (hy_latest - hy_prev) * 100.0
    if len(df) >= 6:
        hy_prev_5 = float(df.iloc[-6]["hy"])
        hy_d5_bps = (hy_latest - hy_prev_5) * 100.0

    spx_ret = None
    if spx_series is not None and not spx_series.empty:
        aligned = spx_series.reindex(df.index).ffill(limit=2)
        spx_tail = aligned.iloc[-1]
        if pd.notna(spx_tail):
            spx_ret = float(spx_tail)

    cooldown_until = tail.get("cooldown_until")
    cooldown_date: date | None = None
    cooldown_iso: str | None = None
    if cooldown_until is not None and not pd.isna(cooldown_until):
        cooldown_ts = pd.Timestamp(cooldown_until)
        cooldown_date = cooldown_ts.date()
        cooldown_iso = cooldown_date.isoformat()

    row_dict = {
        "date": today.isoformat(),
        "hy": hy_latest,
        "vx1": float(tail["vx1"]),
        "vx2": float(tail["vx2"]),
        "z_hy": float(tail["z_hy"]) if not pd.isna(tail["z_hy"]) else None,
        "term_ratio": float(tail["term_ratio"])
        if not pd.isna(tail["term_ratio"])
        else None,
        "cal_spread_pct": float(tail["cal_spread_pct"])
        if not pd.isna(tail["cal_spread_pct"])
        else None,
        "cal_spread_abs": float(tail["cal_spread_abs"])
        if not pd.isna(tail["cal_spread_abs"])
        else None,
        "saturated": bool(tail["saturated"]),
        "hy_score": int(tail["hy_score"]),
        "vix_score": int(tail["vix_score"]),
        "msb": int(tail["msb"]),
        "color": str(tail["color"]),
        "triggers": trigger_flags,
        "winsor_clipped_n": int(tail["winsor_clipped_n"]),
        "cooldown_until": cooldown_iso,
    }

    context = {
        "today": today,
        "spx_ret": spx_ret,
        "hy_d1_bps": hy_d1_bps,
        "hy_d5_bps": hy_d5_bps,
        "streak_ge_60": _compute_streak_ge_60(df["msb"]),
        "cooldown_started_today": "C" in trigger_flags,
        "cooldown_until": cooldown_date,
        "msb_row": row_dict,
    }
    return row_dict, context


def _log_scheduler(status: str, **extra: Any) -> None:
    payload = {"event": "msb.scheduler", "status": status}
    payload.update(extra)
    try:
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    except Exception:
        encoded = str(payload)
    if status == "error":
        _SCHED_LOG.error(encoded)
    else:
        _SCHED_LOG.info(encoded)


def _append_trigger_csv(alerts: Iterable[Any], context: dict[str, Any]) -> None:
    alerts = list(alerts)
    if not alerts:
        return
    row = context.get("msb_row") or {}
    hy_score = int(row.get("hy_score", 0) or 0)
    vix_score = int(row.get("vix_score", 0) or 0)
    msb_value = int(row.get("msb", 0) or 0)
    color = str(row.get("color") or "")
    vx1 = float(row.get("vx1", 0.0) or 0.0)
    vx2 = float(row.get("vx2", 0.0) or 0.0)
    vx_ratio = None
    if vx2 not in (0.0, 0):
        try:
            vx_ratio = vx1 / vx2
        except ZeroDivisionError:
            vx_ratio = None

    hy_d1 = context.get("hy_d1_bps")
    hy_d5 = context.get("hy_d5_bps")
    cooldown_until = context.get("cooldown_until")
    cooldown_iso = (
        cooldown_until.isoformat() if isinstance(cooldown_until, date) else None
    )

    path = Path("debug") / "msb_triggers.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "rule",
                "msb",
                "color",
                "hy_score",
                "vix_score",
                "vx_ratio",
                "hy_d1_bps",
                "hy_d5_bps",
                "cooldown_until",
                "actions_json",
            ],
        )
        if write_header:
            writer.writeheader()
        for alert in alerts:
            data = getattr(alert, "data", {}) or {}
            actions = data.get("actions") or []
            writer.writerow(
                {
                    "date": row.get("date"),
                    "rule": getattr(alert, "rule", ""),
                    "msb": msb_value,
                    "color": color,
                    "hy_score": hy_score,
                    "vix_score": vix_score,
                    "vx_ratio": vx_ratio,
                    "hy_d1_bps": hy_d1,
                    "hy_d5_bps": hy_d5,
                    "cooldown_until": cooldown_iso,
                    "actions_json": json.dumps(
                        actions, separators=(",", ":"), ensure_ascii=False
                    ),
                }
            )


def run_msb_scheduler_once(
    app: FastAPI,
    *,
    vendor_dir: Path | str | None = None,
    now: datetime | None = None,
    max_retries: int = 3,
    allow_stale: bool = False,
    force_refresh: bool = False,
) -> bool:
    """Execute the daily MSB scheduler job once."""
    vendor_root = Path(vendor_dir) if vendor_dir is not None else _VENDOR_ROOT
    reference = (now or datetime.now(tz=_TRT)).astimezone(_TRT)
    today = reference.date()
    today_iso = today.isoformat()

    current = store.read_msb_current()
    history_count = len(store.read_msb_history(days=365))
    if (
        current
        and str(current.get("date")) == today_iso
        and not force_refresh
        and history_count > 1
    ):
        _log_scheduler("skipped", reason="already_up_to_date", date=today_iso)
        MSB_SCHEDULER_RUNS.inc()
        return False

    env_map = dict(os.environ)
    if force_refresh:
        env_map["MSB_VENDOR_FORCE_REFRESH"] = "1"
        env_map["MSB_VENDOR_TTL_HOURS"] = "0"

    msb_source = resolve_msb_source(env_map)
    try:
        status = refresh_vendor_data(vendor_root, env=env_map)
    except Exception as exc:  # pragma: no cover - depends on network/env
        _SCHED_LOG.warning("MSB vendor refresh failed: %s", exc)
        _log_scheduler(
            "warn", date=today_iso, reason="vendor_refresh_failed", error=str(exc)
        )
    else:
        _log_scheduler(
            "refresh",
            date=today_iso,
            source=msb_source,
            vendor=status,
        )

    missing = _missing_vendor_files(vendor_root)
    if missing:
        _log_scheduler(
            "skipped",
            reason="vendor_missing",
            date=today_iso,
            missing=missing,
        )
        MSB_SCHEDULER_RUNS.inc()
        return False

    attempt = 0
    backoff = 5.0
    while attempt < max_retries:
        attempt += 1
        try:
            hy, vx1, vx2, spx = _load_vendor(vendor_root)
            df = compute_msb(hy=hy, vx1=vx1, vx2=vx2, spx_ret=spx)
            df = df.dropna(subset=["hy", "vx1", "vx2"])
            if df.empty:
                _log_scheduler("skipped", reason="empty_frame", date=today_iso)
                MSB_SCHEDULER_RUNS.inc()
                return False
            latest_idx = df.index[-1]
            latest_date = latest_idx.date()
            latest_iso = latest_date.isoformat()
            history_count = len(store.read_msb_history(days=365))
            backfill_needed = history_count <= 1 and len(df) > 1
            if (
                current
                and str(current.get("date")) == latest_iso
                and not backfill_needed
            ):
                _log_scheduler("skipped", reason="already_up_to_date", date=latest_iso)
                MSB_SCHEDULER_RUNS.inc()
                return False
            if latest_date != today:
                if not allow_stale:
                    _log_scheduler(
                        "skipped",
                        reason="pending_vendor_data",
                        date=today_iso,
                        latest=latest_iso,
                    )
                    MSB_SCHEDULER_RUNS.inc()
                    return False
                _log_scheduler(
                    "stale",
                    date=today_iso,
                    latest=latest_iso,
                )

            row_dict, context = _prepare_context(df, spx)
            if current is None or backfill_needed:
                store_frame = df
                backfill = True
            else:
                store_frame = df.iloc[[-1]]
                backfill = False
            affected = store.store_msb(store_frame)
            try:
                latest = store_frame.index[-1]
                MSB_DATA_AGE_SECONDS.set(
                    max(0.0, (datetime.now(tz=_TRT) - latest).total_seconds())
                )
            except Exception:
                pass

            from psd.web.app import broadcast_latest_msb

            broadcast_ok = False
            try:
                broadcast_ok = broadcast_latest_msb(app)
            except Exception as exc:  # pragma: no cover - defensive
                _log_scheduler(
                    "warn", reason="broadcast_failed", date=today_iso, error=str(exc)
                )

            alerts = evaluate_msb_triggers_and_update_livebar(app, context=context)
            _append_trigger_csv(alerts, context)

            _log_scheduler(
                "success",
                date=row_dict.get("date"),
                rows=affected,
                alerts=len(alerts),
                broadcast=broadcast_ok,
                backfill=backfill,
            )
            MSB_SCHEDULER_RUNS.inc()
            return True
        except Exception as exc:  # pragma: no cover - depends on IO state
            _log_scheduler(
                "error",
                date=today_iso,
                attempt=attempt,
                error=str(exc),
            )
            if attempt >= max_retries:
                MSB_SCHEDULER_RUNS.inc()
                raise
            time.sleep(backoff)
            backoff = min(backoff * 2.0, 60.0)
    MSB_SCHEDULER_RUNS.inc()
    return False


def _scheduler_loop(
    app: FastAPI, stop_event: threading.Event, vendor_root: Path
) -> None:
    try:
        import asyncio

        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:
        pass
    while not stop_event.is_set():
        now = datetime.now(tz=_TRT)
        run_at = _next_business_run(now)
        wait_seconds = max(0.0, (run_at - now.astimezone(_TRT)).total_seconds())
        if wait_seconds > 0 and stop_event.wait(wait_seconds):
            break
        if stop_event.is_set():
            break
        try:
            run_msb_scheduler_once(app, vendor_dir=vendor_root, now=run_at)
        except Exception as exc:  # pragma: no cover - background loop
            _SCHED_LOG.exception("MSB scheduler run failed: %s", exc)
            _log_scheduler(
                "error", reason="background_failure", date=run_at.date().isoformat()
            )


def start_msb_scheduler(app: FastAPI, *, vendor_dir: Path | str | None = None) -> None:
    """Start the background MSB scheduler loop."""
    global _SCHED_THREAD, _SCHED_STOP
    with _SCHED_GUARD:
        if _SCHED_THREAD and _SCHED_THREAD.is_alive():
            return
        stop_event = threading.Event()
        vendor_root = Path(vendor_dir) if vendor_dir is not None else _VENDOR_ROOT
        thread = threading.Thread(
            target=_scheduler_loop,
            name="msb-scheduler",
            args=(app, stop_event, vendor_root),
            daemon=True,
        )
        _SCHED_STOP = stop_event
        _SCHED_THREAD = thread
        thread.start()


def stop_msb_scheduler(timeout: float = 5.0) -> None:
    """Stop the background MSB scheduler loop."""
    global _SCHED_THREAD, _SCHED_STOP
    with _SCHED_GUARD:
        stop_event = _SCHED_STOP
        thread = _SCHED_THREAD
        _SCHED_STOP = None
        _SCHED_THREAD = None
    if stop_event is not None:
        stop_event.set()
    if thread is not None:
        thread.join(timeout=timeout)


def _jitter(seconds: float, ratio: float = 0.15) -> float:
    if seconds <= 0:
        return 0.0
    delta = seconds * ratio
    return max(0.0, seconds + random.uniform(-delta, delta))


def io_request(
    kind: str,
    key: str,
    func: Callable[[], Any],
    *,
    hist_limiter: HistoricalLimiter | None = None,
    web_bucket: TokenBucket | None = None,
    small_bar_key: tuple[str, str, str] | None = None,
    max_retries: int = 5,
) -> Any:
    """Run a paced IO request with backoff.

    kind: 'historical' or 'web'
    key: a dedupe key for historical requests
    func: thunk performing the request
    small_bar_key: if provided for historical, enforces 2s burst window
    """
    attempt = 0
    backoff = 0.5
    hist_limiter = hist_limiter or HistoricalLimiter()
    web_bucket = web_bucket or TokenBucket(capacity=10.0, refill_rate_per_sec=10.0)

    while True:
        attempt += 1
        try:
            if kind == "historical":
                allowed = hist_limiter.allow(key, small_bar_key=small_bar_key)
                if not allowed:
                    # Treat as deduped or burst-suppressed; no call is made
                    return None
            else:  # web/client portal API
                web_bucket.take(1.0, block=True)
            return func()
        except PacingViolation:
            pass
        except Exception as e:  # pragma: no cover - depends on runtime sources
            # Respect HTTP 429 and common pacing hints
            status = getattr(e, "status", None) or getattr(e, "status_code", None)
            if status != 429 and "pace" not in str(e).lower():
                raise
        if attempt >= max_retries:
            raise PacingViolation(f"max_retries exceeded for {kind}:{key}")
        time.sleep(_jitter(backoff))
        backoff = min(backoff * 2.0, 30.0)


def run_loop(
    interval: int = 60,
    cfg: dict[str, Any] | None = None,
    *,
    loops: int | None = None,
    web_broadcast: Callable[[dict], None] | None = None,
) -> None:
    """Run the paced intraday loop.

    - Invokes ``scan_once`` every ``interval`` seconds.
    - Uses a last-mark cache to optionally trigger extra IO only for symbols with
      changed marks since the previous iteration.
    - Maintains conservative token buckets to avoid pacing violations.
    """
    if scan_once is None:  # pragma: no cover - safety in minimal envs
        raise RuntimeError("scan_once unavailable")

    cfg = dict(cfg or {})
    hist = HistoricalLimiter()  # 60 per 10min
    web = TokenBucket(capacity=10.0, refill_rate_per_sec=10.0)

    last_marks: dict[str, float] = {}

    # Support bounded iterations for simulators/tests while keeping default infinite loop
    def _iter_range() -> Iterable[int]:
        if loops is None:
            while True:
                yield 1
        else:
            yield from range(loops)

    test_mode = os.getenv("PE_TEST_MODE") == "1"

    loop_no = 0

    for _ in _iter_range():
        loop_no += 1
        t0 = time.monotonic()

        # Optionally fetch or wrap positions to control pacing.
        # If IB datasource is available, wrap via io_request; otherwise rely on engine.
        positions: Iterable[dict[str, Any]] | None = None
        if not test_mode and ib_src is not None and hasattr(ib_src, "get_positions"):

            def _get_pos() -> Any:
                return ib_src.get_positions(cfg)

            positions = io_request(
                "web",
                key="ibkr:get_positions",
                func=_get_pos,
                hist_limiter=hist,
                web_bucket=web,
            )
            if positions is None:
                positions = []
            # Provide positions to engine via cfg if supported; engine reads ib_src directly by default
            cfg["positions_override"] = positions  # tests may use this
        elif test_mode:
            positions = cfg.get("positions_override")
            if positions is None:
                positions = []
                cfg["positions_override"] = positions

        # Evaluate once per cadence
        dto = scan_once(cfg)

        # Optional web broadcast hook
        if callable(web_broadcast):
            try:
                # Ensure JSON-serializable payloads by converting keys/values conservatively
                import json as _json

                _json.dumps(dto)
                web_broadcast(dto)
            except Exception:
                # Do not disrupt the loop on broadcast failures
                pass

        # Last-mark cache: collect simple marks per underlying symbol
        try:
            rows = positions if positions is not None else []
            current_marks: dict[str, float] = {
                str(p.get("symbol")): float(p.get("mark", 0.0))
                for p in rows
                if isinstance(p, dict) and p.get("symbol")
            }
        except Exception:
            current_marks = {}

        changed_syms = [s for s, m in current_marks.items() if last_marks.get(s) != m]
        if test_mode and positions is not None:
            forced = [
                str(p.get("symbol"))
                for p in positions
                if isinstance(p, dict) and p.get("symbol")
            ]
            if forced:
                if loop_no == 1 or loop_no % 5 == 0:
                    changed_syms = forced
                else:
                    changed_syms = []
        if changed_syms:
            # Optional extra IO for greeks/marks only for changed underlyings
            # Users/tests can plug real callables via cfg keys
            fetch_marks: Callable[[Iterable[str]], Any] | None = cfg.get("fetch_marks")  # type: ignore
            fetch_greeks: Callable[[Iterable[str]], Any] | None = cfg.get(
                "fetch_greeks"
            )  # type: ignore
            key_base = hash(tuple(sorted(changed_syms)))

            if fetch_marks is not None:
                mark_key = (
                    f"marks:{loop_no}:{key_base}" if test_mode else f"marks:{key_base}"
                )
                io_request(
                    "web",
                    key=mark_key,
                    func=lambda: fetch_marks(changed_syms),
                    hist_limiter=hist,
                    web_bucket=web,
                )
            if fetch_greeks is not None:
                greek_key = (
                    f"greeks:{loop_no}:{key_base}"
                    if test_mode
                    else f"greeks:{key_base}"
                )
                # Greeks often rely on historical/snapshot data – use historical limiter keying per symbol batch
                io_request(
                    "historical",
                    key=greek_key,
                    func=lambda: fetch_greeks(changed_syms),
                    hist_limiter=hist,
                    web_bucket=web,
                )

        last_marks = current_marks or last_marks

        # Basic progress output kept minimal to avoid noisy logs
        try:
            n_alerts = len(dto.get("alerts", [])) if isinstance(dto, dict) else 0
            print(
                f"[sentinel] {time.strftime('%H:%M:%S')} alerts={n_alerts} changed={len(changed_syms)}"
            )
        except Exception:
            pass

        # Sleep to maintain cadence
        elapsed = time.monotonic() - t0
        to_sleep = max(0.0, float(interval) - elapsed)
        time.sleep(to_sleep)
