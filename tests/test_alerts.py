from __future__ import annotations

import json
from pathlib import Path

from portfolio_exporter.scripts import micro_momo_analyzer as mma


def test_alerts_json_only(tmp_path: Path, monkeypatch) -> None:
    # Use existing fixtures; force csv-only mode and json-only alerts
    posted = {"called": False}

    def fake_emit(alerts, url, dry_run, offline):  # noqa: ANN001
        posted["called"] = True
        return {"sent": 0, "failed": []}

    monkeypatch.setattr("portfolio_exporter.core.alerts.emit_alerts", fake_emit)

    out_dir = tmp_path / "out"
    mma.run(
        cfg_path="tests/data/micro_momo_config.json",
        input_csv="tests/data/meme_scan_sample.csv",
        chains_dir="tests/data",
        out_dir=str(out_dir),
        emit_json=False,
        no_files=True,
        data_mode="csv-only",
        providers=["ib", "yahoo"],
        offline=False,
        halts_source=None,
        webhook="http://example.com",
        alerts_json_only=True,
        ib_basket_out=None,
    )
    alerts_path = out_dir / "micro_momo_alerts.json"
    assert alerts_path.exists()
    data = json.loads(alerts_path.read_text())
    assert isinstance(data, list)
    assert posted["called"] is False  # no POST when alerts_json_only


def test_alerts_offline_no_post(tmp_path: Path, monkeypatch) -> None:
    posted = {"called": False}

    def fake_emit(alerts, url, dry_run, offline):  # noqa: ANN001
        posted["called"] = True
        return {"sent": 0, "failed": []}

    monkeypatch.setattr("portfolio_exporter.core.alerts.emit_alerts", fake_emit)

    out_dir = tmp_path / "out2"
    mma.run(
        cfg_path="tests/data/micro_momo_config.json",
        input_csv="tests/data/meme_scan_sample.csv",
        chains_dir="tests/data",
        out_dir=str(out_dir),
        emit_json=False,
        no_files=True,
        data_mode="csv-only",
        providers=["ib", "yahoo"],
        offline=True,
        halts_source=None,
        webhook="http://example.com",
        alerts_json_only=False,
        ib_basket_out=None,
    )
    assert (out_dir / "micro_momo_alerts.json").exists()
    assert posted["called"] is False  # no POST when offline

