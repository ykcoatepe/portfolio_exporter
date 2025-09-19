"""Simulator for PSD sentinel scheduler pacing/backoff.

Runs a short, controlled loop with synthetic positions to exercise:
- Token bucket/web pacing
- Historical 60/10min limiter with 15s dedupe
- Exponential backoff on 429/pacing
- Last-mark cache triggering marks/greeks only on changed symbols

Usage:
  python3 scripts/sim_sentinel_sched.py --loops 5 --interval 1 --positions 100
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from collections.abc import Iterable
from typing import Any

# Ensure project root is on sys.path so 'src' package is resolvable when
# running this script directly.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.psd.datasources import ibkr as ib_src
from src.psd.sentinel.engine import scan_once
from src.psd.sentinel.sched import HistoricalLimiter, TokenBucket, io_request


class Sim429(Exception):
    def __init__(self, msg: str = "too many requests") -> None:
        super().__init__(msg)
        self.status_code = 429


def _mk_positions(n: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(1, n + 1):
        sym = f"SYM{i:03d}"
        out.append(
            {
                "uid": f"{sym}-eq",
                "symbol": sym,
                "sleeve": "theta",
                "kind": "equity",
                "qty": 1,
                "mark": round(100 + random.random() * 10, 2),
            }
        )
    return out


def _jitter_marks(rows: list[dict[str, Any]], change_ratio: float = 0.2) -> None:
    k = max(1, int(len(rows) * change_ratio))
    for p in random.sample(rows, k=k):
        delta = random.uniform(-0.5, 0.5)
        p["mark"] = round(float(p["mark"]) + delta, 2)


def main() -> None:
    ap = argparse.ArgumentParser(description="Simulate PSD scheduler pacing")
    ap.add_argument("--loops", type=int, default=5, help="Number of iterations")
    ap.add_argument("--interval", type=float, default=1.0, help="Seconds per iteration")
    ap.add_argument("--positions", type=int, default=100, help="Synthetic positions count")
    ap.add_argument(
        "--change-ratio", type=float, default=0.2, help="Fraction of symbols that change each loop"
    )
    args = ap.parse_args()

    positions = _mk_positions(args.positions)
    last_marks: dict[str, float] = {}

    # Monkeypatch get_positions
    def _get_positions(_cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return positions

    ib_src.get_positions = _get_positions  # type: ignore

    # Pace controllers
    hist = HistoricalLimiter()
    web = TokenBucket(capacity=10.0, refill_rate_per_sec=10.0)

    # Marks/Greeks fetchers that sometimes raise 429 to exercise backoff
    counters = {"marks_calls": 0, "greeks_calls": 0, "dup_hist_skips": 0}

    def fetch_marks(symbols: Iterable[str]) -> None:
        counters["marks_calls"] += 1
        # 10% chance of 429 to trigger backoff
        if random.random() < 0.1:
            raise Sim429()
        time.sleep(0.01)

    def fetch_greeks(symbols: Iterable[str]) -> None:
        counters["greeks_calls"] += 1
        if random.random() < 0.1:
            raise Sim429()
        time.sleep(0.02)

    cfg: dict[str, Any] = {"fetch_marks": fetch_marks, "fetch_greeks": fetch_greeks}

    for i in range(1, args.loops + 1):
        t0 = time.monotonic()

        # Move some marks to create deltas
        _jitter_marks(positions, change_ratio=args.change_ratio)

        # One scan
        dto = scan_once(cfg)
        _ = dto.get("alerts", [])

        # Collect current marks from synthetic positions
        current_marks: dict[str, float] = {p["symbol"]: float(p["mark"]) for p in positions}
        changed_syms = [s for s, m in current_marks.items() if last_marks.get(s) != m]

        if changed_syms:
            io_request(
                "web",
                key=f"marks:{hash(tuple(sorted(changed_syms)))}",
                func=lambda: fetch_marks(changed_syms),
                hist_limiter=hist,
                web_bucket=web,
            )
            io_request(
                "historical",
                key=f"greeks:{hash(tuple(sorted(changed_syms)))}",
                func=lambda: fetch_greeks(changed_syms),
                hist_limiter=hist,
                web_bucket=web,
            )

        # Explicit historical duplicate to demonstrate 15s dedupe
        _ = io_request("historical", key="dup-test", func=lambda: None, hist_limiter=hist, web_bucket=web)
        r2 = io_request("historical", key="dup-test", func=lambda: None, hist_limiter=hist, web_bucket=web)
        if r2 is None:
            counters["dup_hist_skips"] += 1

        last_marks = current_marks

        elapsed = time.monotonic() - t0
        to_sleep = max(0.0, float(args.interval) - elapsed)
        print(
            f"[sim] loop={i} changed={len(changed_syms)} marks_calls={counters['marks_calls']} "
            f"greeks_calls={counters['greeks_calls']} dup_skips={counters['dup_hist_skips']} elapsed={elapsed:.3f}s"
        )
        time.sleep(to_sleep)

    print("\nSimulation done.")
    print(
        f"marks_calls={counters['marks_calls']} greeks_calls={counters['greeks_calls']} "
        f"dup_hist_skips={counters['dup_hist_skips']}"
    )


if __name__ == "__main__":
    main()
