from __future__ import annotations

from pathlib import Path

from scripts import psd_perf_harness


def test_run_benchmark_500_fixture() -> None:
    fixture = Path("tests/data/psd_snapshot_500.json")
    result = psd_perf_harness.run_benchmark(iterations=2, fixture=fixture)
    assert result["iterations"] == 2
    assert result["avg_ms"] >= 0.0
    assert result["p95_ms"] >= 0.0
    stats = result["stats"] or {}
    assert stats["option_legs_count"] == 500
    assert stats["combos_matched"] == 125
    assert stats["stale_quotes_count"] == 12
    assert Path(result["fixture"]).resolve() == fixture.resolve()
