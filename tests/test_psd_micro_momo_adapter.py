from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from psd.analyzers.base import AnalyzerResult, Candidate
from psd.runtime.registry import create_analyzer

import psd.plugins.micro_momo_adapter  # ensure registration via side-effect


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for key in [
        "MOMO_INPUT",
        "MOMO_CHAINS_DIR",
        "MOMO_OUT",
        "MOMO_CFG",
        "MOMO_DATA_MODE",
        "MOMO_OFFLINE",
        "MOMO_SESSION",
    ]:
        monkeypatch.delenv(key, raising=False)
    yield
    for key in [
        "MOMO_INPUT",
        "MOMO_CHAINS_DIR",
        "MOMO_OUT",
        "MOMO_CFG",
        "MOMO_DATA_MODE",
        "MOMO_OFFLINE",
        "MOMO_SESSION",
    ]:
        assert key not in os.environ


def _write_summary(out_dir: Path, payload: dict[str, object]) -> Path:
    path = out_dir / "micro_momo_summary.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_micro_momo_adapter_json_only_builds_signals(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def _fake_run(**kwargs):
        captured["kwargs"] = kwargs
        assert os.environ.get("MOMO_OUT") == str(tmp_path)
        assert os.environ.get("MOMO_DATA_MODE") == "offline"
        return [
            {
                "symbol": "ABC",
                "raw_score": "7.5",
                "rvol": "2.2",
                "entry_trigger": "VWAP reclaim",
                "tier": "A",
                "direction": "long",
                "tp": "15.0",
                "sl": "11.5",
                "session_state": "premarket",
                "structure_template": "DebitCall",
            }
        ]

    monkeypatch.setattr("portfolio_exporter.scripts.micro_momo_analyzer.run", _fake_run)

    analyzer = create_analyzer(
        "micro_momo_analyzer",
        output_dir=str(tmp_path),
        json_only=True,
        symbols=["abc"],
    )

    result = analyzer.analyze(
        Candidate(
            identifier="req",
            payload={"env_overrides": {"MOMO_SESSION": "premarket"}},
        )
    )

    assert isinstance(result, AnalyzerResult)
    assert len(result.signals) == 1
    signal = result.signals[0]
    assert signal.name == "micro-momo/ABC"
    assert signal.score == pytest.approx(2.2)
    assert signal.metadata["triggers"]["entry"] == "VWAP reclaim"
    summary = result.notes["summary"]
    assert summary["count"] == 1
    assert summary["mode"] == "json-only"
    kwargs = captured["kwargs"]
    assert kwargs["no_files"] is True
    assert kwargs["prebuilt_scans"] is not None


def test_micro_momo_adapter_collects_artifacts(monkeypatch, tmp_path):
    expected = {
        "scored_csv": "micro_momo_scored.csv",
        "orders_csv": "micro_momo_orders.csv",
        "journal_json": "micro_momo_journal.json",
        "basket_csv": "micro_momo_basket.csv",
        "dashboard_html": "micro_momo_dashboard.html",
    }
    for filename in expected.values():
        (tmp_path / filename).write_text("stub", encoding="utf-8")

    def _fake_run(**kwargs):
        return []

    monkeypatch.setattr("portfolio_exporter.scripts.micro_momo_analyzer.run", _fake_run)

    analyzer = create_analyzer(
        "micro_momo_analyzer",
        output_dir=str(tmp_path),
        json_only=False,
        full_artifacts=True,
    )

    result = analyzer.analyze(Candidate(identifier="req", payload={}))

    assert isinstance(result, AnalyzerResult)
    recorded = result.notes.get("artifacts")
    assert recorded is not None
    for key, filename in expected.items():
        assert recorded[key] == str(tmp_path / filename)
    assert set(recorded) == set(expected)


def test_micro_momo_adapter_applies_cfg_overrides(monkeypatch, tmp_path):
    cfg_snapshot: dict[str, object] = {}

    def _fake_run(**kwargs):
        cfg_path = kwargs["cfg_path"]
        assert cfg_path is not None and Path(cfg_path).exists()
        cfg_snapshot["path"] = cfg_path
        with open(cfg_path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["filters"]["rvol_min"] == 1.5
        return []

    monkeypatch.setattr("portfolio_exporter.scripts.micro_momo_analyzer.run", _fake_run)

    overrides = {"filters": {"rvol_min": 1.5}}
    analyzer = create_analyzer(
        "micro_momo_analyzer",
        output_dir=str(tmp_path),
        cfg_overrides=overrides,
    )

    result = analyzer.analyze(Candidate(identifier="req", payload={}))
    assert isinstance(result, AnalyzerResult)
    assert result.notes["summary"]["cfg_overrides"] == overrides
    cfg_path = Path(cfg_snapshot["path"])
    assert not cfg_path.exists()


def test_micro_momo_adapter_derives_signals_from_summary_strength(
    monkeypatch, tmp_path
):
    summary_payload = {
        "generated_at": "2025-01-01T00:00:00Z",
        "candidates": [
            {
                "symbol": "XYZ",
                "tier": "B",
                "direction": "long",
                "score": 1.25,
                "strength": 3.9,
                "passes_filter": True,
                "session": "premarket",
                "triggers": {"entry": "VWAP reclaim"},
            }
        ],
    }
    summary_path = _write_summary(tmp_path, summary_payload)

    monkeypatch.setattr(
        "portfolio_exporter.scripts.micro_momo_analyzer.run", lambda **_: []
    )

    analyzer = create_analyzer(
        "micro_momo_analyzer", output_dir=str(tmp_path), json_only=True
    )
    result = analyzer.analyze(Candidate(identifier="req", payload={}))

    assert isinstance(result, AnalyzerResult)
    assert len(result.signals) == 1
    signal = result.signals[0]
    assert signal.score == pytest.approx(3.9)
    assert signal.metadata["triggers"]["entry"] == "VWAP reclaim"
    assert result.notes["summary"]["source_path"] == str(summary_path)
    assert result.notes["summary"]["count"] == 1


def test_micro_momo_adapter_uses_disk_summary_when_results_none(
    monkeypatch, tmp_path
) -> None:
    summary_payload = {
        "candidates": [
            {
                "symbol": "DEF",
                "direction": "short",
                "score": 2.5,
                "strength": 2.5,
                "tier": "A",
                "session": "rth",
                "triggers": {"entry": "Trend break"},
            }
        ]
    }
    _write_summary(tmp_path, summary_payload)

    monkeypatch.setattr(
        "portfolio_exporter.scripts.micro_momo_analyzer.run", lambda **_: None
    )

    analyzer = create_analyzer("micro_momo_analyzer", output_dir=str(tmp_path))
    result = analyzer.analyze(Candidate(identifier="req", payload={}))

    assert len(result.signals) == 1
    assert result.notes["summary"]["count"] == 1
    assert result.notes["candidates"][0].identifier == "DEF"


def test_micro_momo_adapter_env_overrides_take_precedence(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def _fake_run(**kwargs):
        captured["env"] = {
            key: os.environ.get(key) for key in ["MOMO_OFFLINE", "MOMO_DATA_MODE"]
        }
        captured["kwargs"] = kwargs
        return []

    monkeypatch.setattr("portfolio_exporter.scripts.micro_momo_analyzer.run", _fake_run)

    analyzer = create_analyzer(
        "micro_momo_analyzer", output_dir=str(tmp_path), json_only=True
    )
    analyzer.analyze(
        Candidate(identifier="req", payload={"env_overrides": {"MOMO_OFFLINE": "0"}})
    )

    assert captured["env"]["MOMO_OFFLINE"] == "0"
    assert captured["kwargs"]["offline"] is False


def test_micro_momo_adapter_factory_kwargs_only(monkeypatch, tmp_path):
    payload = {
        "symbol": "GHI",
        "raw_score": 7.0,
        "direction": "long",
        "tier": "A",
        "session_state": "rth",
        "entry_trigger": "Momentum",
    }

    monkeypatch.setattr(
        "portfolio_exporter.scripts.micro_momo_analyzer.run", lambda **_: [payload]
    )

    analyzer = create_analyzer(
        "micro_momo_analyzer",
        symbols=["ghi"],
        output_dir=str(tmp_path),
        json_only=False,
        env_overrides={"MOMO_SESSION": "rth"},
    )

    result = analyzer.analyze(Candidate(identifier="req", payload={}))
    assert len(result.signals) == 1
    assert any(c.identifier == "GHI" for c in result.notes["candidates"])


def test_micro_momo_adapter_perf_under_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "portfolio_exporter.scripts.micro_momo_analyzer.run", lambda **_: []
    )

    analyzer = create_analyzer("micro_momo_analyzer", output_dir=str(tmp_path))
    candidate = Candidate(identifier="req", payload={})

    iterations = 25
    start = time.perf_counter()
    for _ in range(iterations):
        analyzer.analyze(candidate)
    avg_ms = (time.perf_counter() - start) * 1000 / iterations
    assert avg_ms < 50
