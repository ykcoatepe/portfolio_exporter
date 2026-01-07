import json
from datetime import date, datetime
from pathlib import Path

from portfolio_exporter import psd_powerlaw


def _write_snapshot(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _configure_env(monkeypatch, repo_root: Path) -> None:
    monkeypatch.setenv("PSD_POWERLAW_REPO", str(repo_root))
    monkeypatch.setenv("PSD_POWERLAW_OUTPUT_DIR", "output")
    monkeypatch.setenv("PSD_POWERLAW_REFRESH", "0")


def test_powerlaw_snapshot_fresh(monkeypatch, tmp_path):
    repo = tmp_path / "powerlaw"
    output_dir = repo / "output"
    output_dir.mkdir(parents=True)
    _write_snapshot(
        output_dir / "trader_v5_daily_2025-01-03.json",
        {"as_of": "2025-01-03", "plke": 42.0, "equity_weights": {"SPY": 0.5}},
    )

    _configure_env(monkeypatch, repo)
    monkeypatch.setattr(
        psd_powerlaw,
        "_calendar_trading_days",
        lambda reference, lookback: [date(2025, 1, 3)],
    )

    snapshot = psd_powerlaw.load_powerlaw_snapshot(
        now=datetime(2025, 1, 3, 12, tzinfo=psd_powerlaw.TZ_NY)
    )

    assert snapshot is not None
    assert snapshot["stale"] is False
    assert snapshot["as_of"] == "2025-01-03"
    assert snapshot["equity_weights"]["SPY"] == 0.5


def test_powerlaw_plke_band_alpha_alias(monkeypatch, tmp_path):
    repo = tmp_path / "powerlaw"
    output_dir = repo / "output"
    output_dir.mkdir(parents=True)
    _write_snapshot(
        output_dir / "trader_v5_daily_2025-01-03.json",
        {"as_of": "2025-01-03", "plke_band_alpha": "Heating"},
    )

    _configure_env(monkeypatch, repo)
    monkeypatch.setattr(
        psd_powerlaw,
        "_calendar_trading_days",
        lambda reference, lookback: [date(2025, 1, 3)],
    )

    snapshot = psd_powerlaw.load_powerlaw_snapshot(
        now=datetime(2025, 1, 3, 12, tzinfo=psd_powerlaw.TZ_NY)
    )

    assert snapshot is not None
    assert snapshot["plke_band_aplh"] == "Heating"


def test_powerlaw_snapshot_stale(monkeypatch, tmp_path):
    repo = tmp_path / "powerlaw"
    output_dir = repo / "output"
    output_dir.mkdir(parents=True)
    _write_snapshot(
        output_dir / "trader_v5_daily_2025-01-02.json",
        {"as_of": "2025-01-02", "plke": 40.0},
    )

    _configure_env(monkeypatch, repo)
    monkeypatch.setattr(
        psd_powerlaw,
        "_calendar_trading_days",
        lambda reference, lookback: [date(2025, 1, 3)],
    )

    snapshot = psd_powerlaw.load_powerlaw_snapshot(
        now=datetime(2025, 1, 3, 12, tzinfo=psd_powerlaw.TZ_NY)
    )

    assert snapshot is not None
    assert snapshot["stale"] is True
    assert snapshot["stale_reason"] == "behind_trading_day"


def test_powerlaw_snapshot_missing(monkeypatch, tmp_path):
    repo = tmp_path / "powerlaw"
    (repo / "output").mkdir(parents=True)
    _configure_env(monkeypatch, repo)

    snapshot = psd_powerlaw.load_powerlaw_snapshot(
        now=datetime(2025, 1, 3, 12, tzinfo=psd_powerlaw.TZ_NY)
    )

    assert snapshot is not None
    assert snapshot["stale"] is True
    assert snapshot["stale_reason"] == "missing_snapshot"
