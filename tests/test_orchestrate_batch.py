from pathlib import Path

from portfolio_exporter.scripts import orchestrate_dataset as od
from portfolio_exporter.scripts import (
    daily_pulse,
    historic_prices,
    live_feed,
    portfolio_greeks,
)


def _stub_factory(path: Path, name: str):
    def _stub(fmt: str = "csv") -> None:  # type: ignore[unused-argument]
        (path / f"{name}.{fmt}").write_text("data")

    return _stub


def test_orchestrate_dataset_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(od, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(od, "cleanup", lambda files: None)

    monkeypatch.setattr(
        historic_prices, "run", _stub_factory(tmp_path, "historic_prices")
    )
    monkeypatch.setattr(
        portfolio_greeks, "run", _stub_factory(tmp_path, "portfolio_greeks")
    )
    monkeypatch.setattr(live_feed, "run", _stub_factory(tmp_path, "live_feed"))
    monkeypatch.setattr(daily_pulse, "run", _stub_factory(tmp_path, "daily_pulse"))

    od.run()

    out = capsys.readouterr().out
    assert "✅ Overnight batch completed – all files written." in out
    for name in [
        "historic_prices.csv",
        "portfolio_greeks.csv",
        "live_feed.csv",
        "daily_pulse.csv",
    ]:
        assert (tmp_path / name).exists()
