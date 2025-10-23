from __future__ import annotations

import os
import sys


def _ensure_repo_root_on_path() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if root not in sys.path:
        sys.path.insert(0, root)


def test_psd_simulator_pacing_and_backoff() -> None:
    _ensure_repo_root_on_path()
    from scripts.psd_sim import run_sim  # type: ignore

    res = run_sim(loops=40, interval=0.25, positions_n=100)

    # Dedupe identical historical requests within 15s
    assert res["deduped"] > 0
    # Small-bar guard should suppress some burst attempts
    assert res["burst_suppressed"] > 0
    # Backoff should have been triggered and recovered
    assert res["backoffs"] > 0
    # Historical projected rate should be within 60 per 10 minutes
    assert res["projected_10m_rate"] <= 60.0
    # Overall pacing_ok flag
    assert res["pacing_ok"] is True
