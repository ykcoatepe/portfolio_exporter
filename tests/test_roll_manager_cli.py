import argparse
import importlib.util
import pathlib
import types

import pandas as pd


spec = importlib.util.spec_from_file_location(
    "roll_manager",
    pathlib.Path(__file__).resolve().parents[1]
    / "portfolio_exporter/scripts/roll_manager.py",
)
roll_manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roll_manager)


def _stub_spinner(msg, fn, *a, **k):
    return fn(*a, **k)


def _fixtures():
    pos_df = pd.DataFrame(
        {
            "qty": [1, -1, 1, -1, 1, -1],
            "strike": [100, 105, 110, 115, 50, 55],
            "right": ["C", "C", "C", "C", "P", "P"],
            "delta": [0.5, -0.4, 0.6, -0.5, -0.3, 0.2],
            "gamma": [0.1, -0.1, 0.2, -0.2, -0.05, 0.04],
            "theta": [-0.01, 0.01, -0.02, 0.02, 0.01, -0.01],
            "vega": [0.1, -0.1, 0.15, -0.15, -0.05, 0.05],
            "multiplier": [100] * 6,
        },
        index=[1, 2, 3, 4, 5, 6],
    )

    combos_df = pd.DataFrame(
        {
            "underlying": ["AAPL", "AAPL", "MSFT"],
            "expiry": [pd.Timestamp("2025-08-21")] * 3,
            "legs": [[1, 2], [3, 4], [5, 6]],
            "qty": [1, 1, 1],
            "type": ["other", "other", "other"],
        },
        index=[0, 1, 2],
    )

    async def _fake_positions_async():
        return pos_df

    def _fake_detect(_df):
        return combos_df

    def _fake_chain(symbol, expiry, strikes):  # noqa: ARG001
        rows: list[dict] = []
        for s in strikes:
            rows.append(
                {
                    "strike": s,
                    "right": "C",
                    "mid": 1.0,
                    "delta": 0.4,
                    "gamma": 0.1,
                    "theta": -0.02,
                    "vega": 0.15,
                }
            )
            rows.append(
                {
                    "strike": s,
                    "right": "P",
                    "mid": 1.0,
                    "delta": -0.4,
                    "gamma": 0.1,
                    "theta": -0.02,
                    "vega": 0.15,
                }
            )
        return pd.DataFrame(rows)

    return pos_df, _fake_positions_async, _fake_detect, _fake_chain


def _prep(monkeypatch):
    pos_df, fake_positions_async, fake_detect, fake_chain = _fixtures()
    fake_pg = types.SimpleNamespace(
        _load_positions=fake_positions_async,
        load_positions_sync=lambda: pos_df,
    )
    monkeypatch.setattr(roll_manager, "portfolio_greeks", fake_pg)
    monkeypatch.setattr(roll_manager, "run_with_spinner", _stub_spinner)
    monkeypatch.setattr(roll_manager, "detect_combos", fake_detect)
    monkeypatch.setattr(roll_manager, "fetch_chain", fake_chain)
    return pos_df


def test_dry_run_json_only(monkeypatch):
    _prep(monkeypatch)
    ns = argparse.Namespace(
        include_cal=False,
        days=7,
        tenor="all",
        limit_per_underlying=None,
        dry_run=True,
        debug_timings=False,
        no_pretty=True,
        json=True,
        output_dir=None,
        no_files=True,
    )
    summary = roll_manager.cli(ns)
    assert summary["ok"] is True
    assert summary["sections"]["candidates"] > 0
    assert summary["outputs"] == []


def test_with_files(tmp_path, monkeypatch):
    _prep(monkeypatch)
    outdir = tmp_path / ".tmp_rolls"
    ns = argparse.Namespace(
        include_cal=False,
        days=7,
        tenor="all",
        limit_per_underlying=None,
        dry_run=False,
        debug_timings=False,
        no_pretty=True,
        json=True,
        output_dir=str(outdir),
        no_files=False,
    )
    summary = roll_manager.cli(ns)
    assert any("roll_preview" in p for p in summary["outputs"])
    assert any("roll_ticket" in p for p in summary["outputs"])
    assert (outdir / "roll_manager_manifest.json").exists()


def test_limit_per_underlying(monkeypatch):
    _prep(monkeypatch)
    ns = argparse.Namespace(
        include_cal=False,
        days=7,
        tenor="all",
        limit_per_underlying=1,
        dry_run=True,
        debug_timings=False,
        no_pretty=True,
        json=True,
        output_dir=None,
        no_files=True,
    )
    summary = roll_manager.cli(ns)
    assert summary["meta"]["limits"]["per_underlying"] == 1
    counts: dict[str, int] = {}
    for cand in summary["candidates"]:
        counts[cand["underlying"]] = counts.get(cand["underlying"], 0) + 1
    assert all(v <= 1 for v in counts.values())

