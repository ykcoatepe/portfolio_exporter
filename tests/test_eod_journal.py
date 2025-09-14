from __future__ import annotations

import csv
from pathlib import Path

from portfolio_exporter.core.journal import write_journal_template
from portfolio_exporter.scripts.micro_momo_eod import main as eod_main


def test_eod_updates_offline(tmp_path: Path) -> None:
    j = tmp_path / "journal.csv"
    scored = [
        {
            "symbol": "ABC",
            "tier": "A",
            "direction": "long",
            "structure_template": "DebitCall",
            "contracts": 1,
            "expiry": "",
            "long_strike": 12,
            "short_strike": 13,
            "debit_or_credit": 1.0,
            "tp": 1.50,
            "sl": 0.50,
            "entry_trigger": "x",
        }
    ]
    write_journal_template(scored, str(j))
    assert j.exists()
    outdir = tmp_path / "out"
    outdir.mkdir()
    rc = eod_main(["--journal", str(j), "--out_dir", str(outdir), "--offline"])
    assert rc == 0
    rows = list(csv.DictReader(open(j, encoding="utf-8")))
    assert rows[0]["status"] in ("Expired", "Stopped", "Profit")

