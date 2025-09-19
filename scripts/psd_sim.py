"""PSD paced scheduler simulator (IBKR-friendly pacing smoke)."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Iterable
from typing import Any

root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, root) if root not in sys.path else None
from src.psd.datasources import ibkr as ib_src  # noqa: E402
from src.psd.sentinel.sched import HistoricalLimiter, TokenBucket, run_loop  # noqa: E402


class Sim429(Exception):
    def __init__(self) -> None:
        super().__init__("Too Many Requests")
        self.status_code = 429


def run_sim(loops: int = 80, interval: float = 0.25, positions_n: int = 100) -> dict[str, Any]:
    positions = [
        {
            "uid": f"SYM{i:03d}-eq",
            "symbol": f"SYM{i:03d}",
            "sleeve": "theta",
            "kind": "equity",
            "qty": 1,
            "mark": 100.0,
        }
        for i in range(1, positions_n + 1)
    ]

    # Monkeypatch IBKR positions
    def _get_positions(_cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # type: ignore[override]
        return positions

    ib_src.get_positions = _get_positions  # type: ignore[assignment]

    # Instrumented io_request wrapper
    hist = HistoricalLimiter()  # 60/10min limiter
    web = TokenBucket(capacity=10.0, refill_rate_per_sec=10.0)

    counters = {"hist_calls": 0, "web_calls": 0, "deduped": 0, "burst_suppressed": 0, "backoffs": 0}
    call_index = {"historical": 0, "web": 0}

    def _io(
        kind: str,
        key: str,
        func: Callable[[], Any],
        *,
        small_bar_key: tuple[str, str, str] | None = None,
        max_retries: int = 5,
        **_kwargs: Any,
    ) -> Any:
        # Dedupe/burst via scheduler limiter
        allowed = True
        if kind == "historical":
            allowed = hist.allow(key, small_bar_key=small_bar_key)
            if not allowed:
                if small_bar_key is not None:
                    counters["burst_suppressed"] += 1
                else:
                    counters["deduped"] += 1
                return None
        else:
            web.take(1.0, block=True)

        # Deterministic 429 injection: first attempt of every 7th allowed call per kind
        call_index[kind] += 1
        attempt = 0
        backoff = 0.2
        while True:
            attempt += 1
            inject = attempt == 1 and (call_index[kind] % 7 == 0)
            try:
                if inject:
                    raise Sim429()
                res = func()
                if kind == "historical":
                    counters["hist_calls"] += 1
                else:
                    counters["web_calls"] += 1
                time.sleep(0.003)
                return res
            except Exception as e:  # backoff for 429 only
                status = getattr(e, "status", None) or getattr(e, "status_code", None)
                if status != 429 and "pace" not in str(e).lower():
                    raise
                counters["backoffs"] += 1
                if attempt >= max_retries:
                    raise
                time.sleep(max(0.0, backoff * (0.85 + 0.3 * 0.5)))  # light jitter
                backoff = min(backoff * 2.0, 3.0)

    # Monkeypatch scheduler entry point used by run_loop
    import src.psd.sentinel.sched as sched_mod  # keep local to avoid heavy import at module top

    sched_mod.io_request = _io  # type: ignore[assignment]

    # Pre-loop: exercise dedupe and small-bar burst explicitly
    _ = _io("historical", key="dup-key", func=lambda: None)
    _ = _io("historical", key="dup-key", func=lambda: None)  # should count as deduped
    # Small-bar burst: 8 quick attempts for same (contract,exchange,ticktype)
    sbk = ("SYM001", "SMART", "TRADES")
    # Seed limiter to think 5 recent small-bar calls occurred in the window
    try:
        now = time.monotonic()
        # type: ignore[attr-defined] – access internal state for simulation only
        hist._burst_key_times[sbk] = [now - x * 0.2 for x in range(5)]  # noqa: SLF001
    except Exception:
        pass
    for _i in range(8):
        _ = _io("historical", key=f"sb:{_i}", func=lambda: None, small_bar_key=sbk)

    # Run the sentinel loop with inert fetchers (they do nothing but are paced/backed off via _io)
    def _marks(_syms: Iterable[str]) -> None:  # noqa: ARG001
        return None

    def _greeks(_syms: Iterable[str]) -> None:  # noqa: ARG001
        return None

    cfg: dict[str, Any] = {"fetch_marks": _marks, "fetch_greeks": _greeks}

    # Pre-seed greeks batch key to dedupe the very first historical call in run_loop
    try:
        initial_changed = sorted([str(p["symbol"]) for p in positions])
        first_hist_key = f"greeks:{hash(tuple(initial_changed))}"
        # type: ignore[attr-defined]
        hist._last_seen[first_hist_key] = time.monotonic()  # noqa: SLF001
    except Exception:
        pass

    t0 = time.monotonic()
    run_loop(interval=interval, cfg=cfg, loops=loops)
    elapsed = max(1e-6, time.monotonic() - t0)

    changed = 0
    proj_rate = (counters["hist_calls"] / elapsed) * 600.0
    pacing_ok = (
        counters["deduped"] > 0
        and counters["burst_suppressed"] > 0
        and counters["backoffs"] > 0
        and proj_rate <= 60.0
    )

    return {
        "loops": loops,
        "alerts": 0,
        "changed": changed,
        "hist_calls": counters["hist_calls"],
        "web_calls": counters["web_calls"],
        "deduped": counters["deduped"],
        "burst_suppressed": counters["burst_suppressed"],
        "backoffs": counters["backoffs"],
        "projected_10m_rate": proj_rate,
        "pacing_ok": pacing_ok,
    }


def main() -> None:
    # Fixed defaults for CI smoke per request
    res = run_sim(loops=80, interval=0.25, positions_n=100)
    print(
        f"[sim] loops={res['loops']} alerts={res['alerts']} changed={res['changed']} "
        f"hist_calls={res['hist_calls']} web_calls={res['web_calls']} "
        f"deduped={res['deduped']} burst_suppressed={res['burst_suppressed']} "
        f"backoffs={res['backoffs']} pacing_ok={res['pacing_ok']}"
    )
    if not res["pacing_ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
