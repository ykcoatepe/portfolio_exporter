from __future__ import annotations

import os
from pathlib import Path

from src.psd.sentinel.engine import scan_once


def test_rollup_and_eod_digest(tmp_path: Path):
    memo_path = tmp_path / "memos.jsonl"
    cfg = {
        "nav": 100000.0,
        "memo_path": str(memo_path),
        "rollup_digest": True,
        "eod_digest": True,
        "kpi_memos": [{"sleeve": "theta", "R": 0.5, "win": True, "theta_roc": 0.01, "nav": 1000}],
        "day_pl": -0.01,
        "theta_fees_wtd": 120.0,
        "hedge_cost_mtd": 360.0,
        "budgets": {"theta_weekly": 0.001, "hedge_monthly": 0.0035},
    }
    dto = scan_once(cfg)
    assert memo_path.exists()
    content = memo_path.read_text(encoding="utf-8")
    assert "digest_rollup" in content and "digest_eod" in content
    # CLI footer presence is driven by dto -> budgets included
    assert "budgets" in dto

