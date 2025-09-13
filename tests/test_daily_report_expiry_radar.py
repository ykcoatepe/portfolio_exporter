from pathlib import Path
from datetime import datetime

from portfolio_exporter.scripts import daily_report


class FixedDate(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2024, 1, 10)


def _fake_latest_factory(mapping: dict[str, Path]):
    def _latest(name: str, fmt: str = "csv", outdir: str | None = None):
        return mapping.get(name)

    return _latest


def test_expiry_radar_combos(monkeypatch):
    data_dir = Path(__file__).parent / "data"
    mapping = {
        "portfolio_greeks_positions": data_dir / "positions_sample.csv",
        "portfolio_greeks_totals": data_dir / "totals_sample.csv",
        "portfolio_greeks_combos": data_dir / "combos_expiry_sample.csv",
    }
    monkeypatch.setattr("portfolio_exporter.core.io.latest_file", _fake_latest_factory(mapping))
    monkeypatch.setattr(daily_report, "datetime", FixedDate)
    res = daily_report.main(["--json", "--expiry-window", "7"])
    radar = res["expiry_radar"]
    assert radar["basis"] == "combos"
    assert radar["window_days"] == 7
    assert radar["rows"]
    assert any("by_structure" in r for r in radar["rows"])


def test_expiry_radar_positions_fallback(monkeypatch):
    data_dir = Path(__file__).parent / "data"
    mapping = {
        "portfolio_greeks_positions": data_dir / "positions_sample.csv",
    }
    monkeypatch.setattr("portfolio_exporter.core.io.latest_file", _fake_latest_factory(mapping))
    monkeypatch.setattr(daily_report, "datetime", FixedDate)
    res = daily_report.main(["--json", "--expiry-window", "10"])
    radar = res["expiry_radar"]
    assert radar["basis"] == "positions"
    assert radar["rows"]


def test_expiry_radar_symbol_filter(monkeypatch):
    data_dir = Path(__file__).parent / "data"
    mapping = {
        "portfolio_greeks_positions": data_dir / "positions_sample.csv",
        "portfolio_greeks_totals": data_dir / "totals_sample.csv",
        "portfolio_greeks_combos": data_dir / "combos_expiry_sample.csv",
    }
    monkeypatch.setattr("portfolio_exporter.core.io.latest_file", _fake_latest_factory(mapping))
    monkeypatch.setattr(daily_report, "datetime", FixedDate)
    res = daily_report.main(["--json", "--expiry-window", "7", "--symbol", "AAPL"])
    assert res["positions_rows"] == 1
    assert res["combos_rows"] == 1
    assert res["filters"] == {"symbol": "AAPL"}
    radar = res["expiry_radar"]
    assert radar["rows"] and radar["rows"][0]["count"] == 1
    assert radar["rows"][0].get("by_structure", {}) == {"vertical": 1}


def test_expiry_radar_disabled(monkeypatch):
    data_dir = Path(__file__).parent / "data"
    mapping = {
        "portfolio_greeks_positions": data_dir / "positions_sample.csv",
        "portfolio_greeks_combos": data_dir / "combos_expiry_sample.csv",
    }
    monkeypatch.setattr("portfolio_exporter.core.io.latest_file", _fake_latest_factory(mapping))
    monkeypatch.setattr(daily_report, "datetime", FixedDate)
    res = daily_report.main(["--json", "--expiry-window", "0"])
    assert "expiry_radar" not in res
