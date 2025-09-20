from __future__ import annotations

from pathlib import Path

from portfolio_exporter.core.micro_momo_sources import load_chain_csv, load_scan_csv


def test_load_scan_csv(tmp_path: Path) -> None:
    # Use repo fixture
    rows = load_scan_csv("tests/data/meme_scan_sample.csv")
    assert len(rows) >= 2
    assert rows[0].symbol == "ABC"
    assert rows[0].price == 100


def test_load_chain_csv() -> None:
    rows = load_chain_csv("tests/data/ABC_20250115.csv")
    assert any(r.right == "C" for r in rows)
    assert any(r.right == "P" for r in rows)
    assert all(r.symbol == "ABC" for r in rows)

