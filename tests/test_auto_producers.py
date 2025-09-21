from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Dict, Any

from portfolio_exporter.core.micro_momo_types import ScanRow
from portfolio_exporter.scripts import micro_momo_analyzer as mma


def _write_bars_csv(path: Path) -> None:
    rows: List[Dict[str, Any]] = []
    # 10 ascending bars with growing volume
    for i in range(10):
        rows.append(
            {
                "ts": i,
                "open": 9.5 + 0.05 * i,
                "high": 9.6 + 0.05 * i,
                "low": 9.4 + 0.05 * i,
                "close": 9.5 + 0.05 * i,
                "volume": 1000 + 10 * i,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ts", "open", "high", "low", "close", "volume"])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _write_chain_csv(path: Path, symbol: str) -> None:
    rows = [
        {"symbol": symbol, "expiry": "20250115", "right": "C", "strike": 10.0, "bid": 1.0, "ask": 1.2, "last": 1.1, "volume": 100, "oi": 500},
        {"symbol": symbol, "expiry": "20250115", "right": "C", "strike": 10.5, "bid": 0.7, "ask": 0.9, "last": 0.8, "volume": 50, "oi": 300},
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "expiry", "right", "strike", "bid", "ask", "last", "volume", "oi"])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_auto_producers_fill_from_artifacts(monkeypatch, tmp_path: Path) -> None:
    sym = "ABC"
    out_dir = tmp_path / "out"
    chains_dir = tmp_path / "chains"

    # Monkeypatch upstream to create artifacts
    from portfolio_exporter.core import upstream

    def _fake_bars(symbols, timeout=30):
        _write_bars_csv(out_dir / f"{sym}_bars.csv")
        return True

    def _fake_chain(symbols, timeout=30):
        _write_chain_csv(chains_dir / f"{sym}_20250115.csv", sym)
        return True

    monkeypatch.setattr(upstream, "run_live_bars", _fake_bars)
    monkeypatch.setattr(upstream, "run_chain_snapshot", _fake_chain)

    # Synthesize minimal scan
    scans = [
        ScanRow(
            symbol=sym,
            price=10.0,
            volume=0,
            rel_strength=0.0,
            short_interest=0.0,
            turnover=0.0,
            iv_rank=0.0,
            atr_pct=0.0,
            trend=0.0,
        )
    ]

    results = mma.run(
        cfg_path=None,
        input_csv=None,
        chains_dir=str(chains_dir),
        out_dir=str(out_dir),
        emit_json=False,
        no_files=True,
        data_mode="csv-only",
        providers=["ib", "yahoo"],
        offline=True,
        halts_source=None,
        auto_producers=True,
        upstream_timeout_sec=5,
        prebuilt_scans=scans,
    )

    assert results, "Expected one result"
    r = results[0]
    # Bars-derived metrics
    assert r.get("vwap") is not None
    assert r.get("rvol_1m", 0) > 0
    assert r.get("src_vwap") == "artifact"
    assert r.get("src_rvol") == "artifact"
    # Chain-derived metrics
    assert r.get("oi_near_money", 0) > 0
    assert r.get("spread_pct_near_money") is not None
    assert r.get("src_chain_oi") == "artifact"


def test_scored_csv_preserves_enrichment_columns(monkeypatch, tmp_path: Path) -> None:
    sym = "ABC"
    out_dir = tmp_path / "out"
    chains_dir = tmp_path / "chains"

    from portfolio_exporter.core import upstream

    def _fake_bars(symbols, timeout=30):
        _write_bars_csv(out_dir / f"{sym}_bars.csv")
        return True

    def _fake_chain(symbols, timeout=30):
        _write_chain_csv(chains_dir / f"{sym}_20250115.csv", sym)
        return True

    monkeypatch.setattr(upstream, "run_live_bars", _fake_bars)
    monkeypatch.setattr(upstream, "run_chain_snapshot", _fake_chain)

    scans = [
        ScanRow(
            symbol=sym,
            price=10.0,
            volume=0,
            rel_strength=0.0,
            short_interest=0.0,
            turnover=0.0,
            iv_rank=0.0,
            atr_pct=0.0,
            trend=0.0,
        )
    ]

    mma.run(
        cfg_path=None,
        input_csv=None,
        chains_dir=str(chains_dir),
        out_dir=str(out_dir),
        emit_json=False,
        no_files=False,
        data_mode="csv-only",
        providers=["ib", "yahoo"],
        offline=True,
        halts_source=None,
        auto_producers=True,
        upstream_timeout_sec=5,
        prebuilt_scans=scans,
    )

    scored_path = out_dir / "micro_momo_scored.csv"
    assert scored_path.exists()
    with scored_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows, "expected scored rows"
    row = rows[0]
    assert "src_vwap" in row
    assert row["src_vwap"] == "artifact"
    assert "data_errors" in row
    errors = row["data_errors"] or ""
    assert "bars_missing" not in errors
    assert "chain_missing" not in errors
