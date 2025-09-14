from __future__ import annotations

from pathlib import Path

from portfolio_exporter.core.fs_utils import find_latest_chain_for_symbol
from portfolio_exporter.core.micro_momo_sources import load_chain_csv


def test_find_latest_chain_for_symbol(tmp_path: Path) -> None:
    sym = "ABC"
    d = tmp_path / "chains"
    d.mkdir()
    older = d / f"{sym}_20240101.csv"
    newer = d / f"{sym}_20240520.csv"
    older.write_text(
        "symbol,expiry,right,strike,bid,ask,mid,delta,oi,volume\n"
        "ABC,20250124,C,12,1.1,1.2,1.15,0.30,1000,100\n",
        encoding="utf-8",
    )
    newer.write_text(
        "symbol,expiry,right,strike,bid,ask,mid,delta,oi,volume\n"
        "ABC,20250124,C,13,0.6,0.65,0.62,0.08,900,80\n",
        encoding="utf-8",
    )
    best = find_latest_chain_for_symbol(str(d), sym)
    assert best and best.endswith(f"{sym}_20240520.csv")
    rows = load_chain_csv(best)
    assert len(rows) == 1 and rows[0].strike == 13.0

