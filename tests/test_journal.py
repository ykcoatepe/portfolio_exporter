from __future__ import annotations

import csv
from pathlib import Path

from portfolio_exporter.core.journal import JOURNAL_COLS, update_journal, write_journal_template


def test_journal_roundtrip(tmp_path: Path) -> None:
    out = tmp_path / "journal.csv"
    scored = [
        {
            "symbol": "ABC",
            "tier": "A",
            "direction": "long",
            "structure_template": "DebitCall",
            "contracts": 3,
            "expiry": "20250124",
            "long_strike": 12,
            "short_strike": 13,
            "debit_or_credit": 0.8,
            "tp": 1.24,
            "sl": 0.40,
            "entry_trigger": "test",
        }
    ]
    write_journal_template(scored, str(out))
    assert out.exists()
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert rows and set(JOURNAL_COLS).issuperset(rows[0].keys())
    # update
    update_journal(
        str(out),
        {"ABC": {"status": "Triggered", "status_ts": "2025-01-01 10:00:00", "result_R": "0.5"}},
    )
    rows2 = list(csv.DictReader(open(out, encoding="utf-8")))
    assert rows2[0]["status"] == "Triggered" and rows2[0]["result_R"] == "0.5"

