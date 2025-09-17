from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from psd.analytics.stats import compute_stats

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "data" / "psd_snapshot_500.json"
DEFAULT_THRESHOLD_MS = 200.0


def _load_snapshot(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight_upper = k - lower
    weight_lower = 1.0 - weight_upper
    return ordered[lower] * weight_lower + ordered[upper] * weight_upper


def run_benchmark(
    *,
    iterations: int = 15,
    fixture: Path | str | None = None,
) -> dict[str, Any]:
    path = Path(fixture) if fixture else FIXTURE_PATH
    snapshot = _load_snapshot(path)

    durations_ms: list[float] = []
    latest_stats: Optional[Dict[str, Any]] = None

    count = max(1, int(iterations))
    for _ in range(count):
        start = time.perf_counter()
        latest_stats = compute_stats(snapshot)
        durations_ms.append((time.perf_counter() - start) * 1000.0)

    avg_ms = sum(durations_ms) / len(durations_ms)
    p95_ms = _percentile(durations_ms, 0.95)

    return {
        "iterations": len(durations_ms),
        "avg_ms": avg_ms,
        "p95_ms": p95_ms,
        "durations_ms": durations_ms,
        "stats": latest_stats or {},
        "fixture": str(path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PSD performance micro-benchmark")
    parser.add_argument("--iterations", type=int, default=15, help="benchmark iterations (default: 15)")
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH, help="path to snapshot fixture")
    parser.add_argument(
        "--threshold-ms",
        type=float,
        default=DEFAULT_THRESHOLD_MS,
        help="alert threshold for p95 latency in milliseconds",
    )
    args = parser.parse_args(argv)

    result = run_benchmark(iterations=args.iterations, fixture=args.fixture)
    stats = result.get("stats", {}) or {}
    stale_quotes = int(stats.get("stale_quotes_count") or 0)
    combos = int(stats.get("combos_matched") or 0)
    option_legs = int(stats.get("option_legs_count") or 0)

    print(
        (
            "[psd-perf] fixture=%s iterations=%d avg=%.2fms p95=%.2fms "
            "option_legs=%d combos=%d stale_quotes=%d"
        )
        % (
            result.get("fixture"),
            result["iterations"],
            result["avg_ms"],
            result["p95_ms"],
            option_legs,
            combos,
            stale_quotes,
        )
    )

    threshold = args.threshold_ms or DEFAULT_THRESHOLD_MS
    if result["p95_ms"] > threshold:
        print(
            "[psd-perf] ALERT: p95 %.2f ms exceeded %.2f ms threshold" % (result["p95_ms"], threshold),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
