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

import random
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

# Lazy import to keep CLI startup fast and allow test monkeypatching
try:  # pragma: no cover - exercised via scripts
    from ..datasources import ibkr as ib_src
    from .engine import scan_once
except Exception:  # pragma: no cover - minimal envs
    scan_once = None  # type: ignore
    ib_src = None  # type: ignore


class PacingViolation(Exception):
    pass


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

    def take(self, amount: float = 1.0, block: bool = True, timeout: float | None = None) -> bool:
        start = time.monotonic()
        while True:
            with self.lock:
                now = time.monotonic()
                assert self.last_refill is not None and self.tokens is not None
                elapsed = max(0.0, now - self.last_refill)
                self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate_per_sec)
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

    def __init__(self, capacity: int = 60, window_sec: int = 600, dedupe_window: int = 15) -> None:
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

    def allow(self, key: str, small_bar_key: tuple[str, str, str] | None = None) -> bool:
        now = time.monotonic()
        with self.lock:
            self._cleanup(now)
            # Dedupe identical
            if key in self._last_seen and (now - self._last_seen[key]) < self.dedupe_window:
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

    for _ in _iter_range():
        t0 = time.monotonic()

        # Optionally fetch or wrap positions to control pacing.
        # If IB datasource is available, wrap via io_request; otherwise rely on engine.
        positions: Iterable[dict[str, Any]] | None = None
        if ib_src is not None and hasattr(ib_src, "get_positions"):

            def _get_pos() -> Any:
                return ib_src.get_positions(cfg)

            positions = io_request(
                "web", key="ibkr:get_positions", func=_get_pos, hist_limiter=hist, web_bucket=web
            )
            if positions is None:
                positions = []
            # Provide positions to engine via cfg if supported; engine reads ib_src directly by default
            cfg["positions_override"] = positions  # tests may use this

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
        if changed_syms:
            # Optional extra IO for greeks/marks only for changed underlyings
            # Users/tests can plug real callables via cfg keys
            fetch_marks: Callable[[Iterable[str]], Any] | None = cfg.get("fetch_marks")  # type: ignore
            fetch_greeks: Callable[[Iterable[str]], Any] | None = cfg.get("fetch_greeks")  # type: ignore

            if fetch_marks is not None:
                io_request(
                    "web",
                    key=f"marks:{hash(tuple(sorted(changed_syms)))}",
                    func=lambda: fetch_marks(changed_syms),
                    hist_limiter=hist,
                    web_bucket=web,
                )
            if fetch_greeks is not None:
                # Greeks often rely on historical/snapshot data – use historical limiter keying per symbol batch
                io_request(
                    "historical",
                    key=f"greeks:{hash(tuple(sorted(changed_syms)))}",
                    func=lambda: fetch_greeks(changed_syms),
                    hist_limiter=hist,
                    web_bucket=web,
                )

        last_marks = current_marks or last_marks

        # Basic progress output kept minimal to avoid noisy logs
        try:
            n_alerts = len(dto.get("alerts", [])) if isinstance(dto, dict) else 0
            print(f"[sentinel] {time.strftime('%H:%M:%S')} alerts={n_alerts} changed={len(changed_syms)}")
        except Exception:
            pass

        # Sleep to maintain cadence
        elapsed = time.monotonic() - t0
        to_sleep = max(0.0, float(interval) - elapsed)
        time.sleep(to_sleep)
