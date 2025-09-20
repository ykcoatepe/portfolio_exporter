from __future__ import annotations

import csv
import json
from pathlib import Path

from portfolio_exporter.scripts.micro_momo_analyzer import main as mm_main


def test_concurrency_guard(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    # Pre-create a journal with two active names
    j = out / "micro_momo_journal.csv"
    with open(j, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "status"])
        w.writeheader()
        w.writerow({"symbol": "AAA", "status": "Pending"})
        w.writerow({"symbol": "BBB", "status": "Triggered"})

    # Minimal scan CSV for one new name
    scan = tmp_path / "scan.csv"
    scan.write_text(
        "symbol,price,volume,rel_strength,short_interest,turnover,iv_rank,atr_pct,trend\n"
        "XYZ,10,10000,60,5,2,10,1.0,0.2\n",
        encoding="utf-8",
    )
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"max_concurrent": 2}), encoding="utf-8")

    # Run in JSON mode to exercise guard logic; ensure no crash
    mm_main(
        [
            "--input",
            str(scan),
            "--cfg",
            str(cfg),
            "--out_dir",
            str(out),
            "--json",
            "--no-files",
            "--data-mode",
            "csv-only",
        ]
    )


def test_concurrency_guard_marks_overflow(tmp_path: Path, capsys) -> None:
    out = tmp_path / "out"
    out.mkdir()
    scan = tmp_path / "scan.csv"
    scan.write_text(
        "symbol,price,volume,rel_strength,short_interest,turnover,iv_rank,atr_pct,trend\n"
        "ABC,12,10000,60,5,2,10,1.0,0.2\n"
        "XYZ,10,12000,65,5,2,12,1.2,0.3\n",
        encoding="utf-8",
    )
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"max_concurrent": 1}), encoding="utf-8")

    mm_main(
        [
            "--input",
            str(scan),
            "--cfg",
            str(cfg),
            "--out_dir",
            str(out),
            "--json",
            "--no-files",
            "--data-mode",
            "csv-only",
        ]
    )
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data) == 2
    assert data[0].get("concurrency_guard") == 0
    assert data[1].get("concurrency_guard") == 1

