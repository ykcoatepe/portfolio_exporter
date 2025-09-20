from __future__ import annotations

import asyncio
import importlib
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

from psd.core.store import (
    append_event,
    checkpoint,
    init,
    write_health,
    write_snapshot,
)

log = logging.getLogger("psd.ingestor")
HEARTBEAT_S = float(os.getenv("PSD_HEARTBEAT_S", "2.0"))
DEFAULT_CHECKPOINT_EVERY = 300

INGEST_TICK_SECONDS = Histogram("psd_ingest_tick_seconds", "Ingest loop tick duration (s)")
DATA_AGE_SECONDS = Gauge("psd_data_age_seconds", "Age of last good snapshot (s)")
EVENTS_WRITTEN = Counter("psd_events_total", "Events appended", ["kind"])


def _checkpoint_interval() -> int:
    raw = os.getenv("PSD_CHECKPOINT_EVERY", str(DEFAULT_CHECKPOINT_EVERY)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_CHECKPOINT_EVERY
    return max(value, 0)


# Optional: fully-qualified callable to produce a snapshot dict
# e.g. PSD_SNAPSHOT_FN="portfolio_exporter.psd_adapter:snapshot_once"
SNAPSHOT_FN_SPEC = os.getenv("PSD_SNAPSHOT_FN", "").strip()


def _load_callable(spec: str, fallback: Callable[..., Any]) -> Callable[..., Any]:
    """Load a dotted 'module:function' callable or return fallback.

    Uses importlib.import_module per Python docs.
    """
    if not spec:
        return fallback
    if ":" not in spec:
        raise ValueError("Expected 'module:function' in PSD_SNAPSHOT_FN")
    mod_name, fn_name = spec.split(":", 1)
    mod = importlib.import_module(mod_name)  # returns the specified module
    fn = getattr(mod, fn_name)
    if not callable(fn):
        raise TypeError(f"{spec} is not callable")
    return fn


async def _maybe_await(x):
    return await x if asyncio.iscoroutine(x) else x


async def _default_fetch_snapshot() -> dict:
    """Minimal stub so SSE never stays silent; replace via PSD_SNAPSHOT_FN."""
    ts = time.time()
    return {"ts": ts, "positions": [], "quotes": {}, "risk": {}}


# resolve provider once at import-time
_FETCH_SNAPSHOT: Callable[[], Awaitable[dict] | dict] = _load_callable(
    SNAPSHOT_FN_SPEC, _default_fetch_snapshot
)


async def fetch_snapshot() -> dict:
    return await _maybe_await(_FETCH_SNAPSHOT())


async def run() -> None:
    init()
    snapshot_env = os.getenv("PSD_SNAPSHOT_FN")
    log.info(
        "PSD ingestor starting with snapshot_fn=%s | IB %s:%s clientId=%s",
        snapshot_env,
        os.getenv("IB_HOST"),
        os.getenv("IB_PORT"),
        os.getenv("IB_CLIENT_ID"),
    )
    if not snapshot_env:
        log.error("PSD_SNAPSHOT_FN is not set. Falling back may yield empty snapshots.")
    checkpoint_every = _checkpoint_interval()
    last_ok_ts: float = 0.0
    tick_count = 0
    while True:
        ib_ok = False
        tick_count += 1
        with INGEST_TICK_SECONDS.time():
            try:
                snap = await fetch_snapshot()
                if not isinstance(snap, dict) or "ts" not in snap:
                    raise ValueError("snapshot must be a dict with key 'ts'")
                write_snapshot(snap)
                EVENTS_WRITTEN.labels("snapshot").inc()
                append_event("diff", {"ts": snap["ts"]})
                EVENTS_WRITTEN.labels("diff").inc()
                last_ok_ts = time.time()
                ib_ok = True
            except Exception as e:
                log.warning("ingestor tick failed: %s", e, exc_info=False)
        age = (time.time() - last_ok_ts) if last_ok_ts else 1e9
        write_health(ib_ok, age)
        DATA_AGE_SECONDS.set(age)
        if checkpoint_every and tick_count % checkpoint_every == 0:
            try:
                checkpoint("PASSIVE")
            except Exception as exc:  # pragma: no cover - defensive logging
                log.debug("checkpoint failed: %s", exc, exc_info=False)
        await asyncio.sleep(HEARTBEAT_S)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
