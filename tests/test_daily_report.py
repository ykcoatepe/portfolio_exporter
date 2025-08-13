from pathlib import Path

from portfolio_exporter.scripts import daily_report


def _fake_latest_factory(base: Path):
    mapping = {
        "portfolio_greeks_positions": base / "positions_sample.csv",
        "portfolio_greeks_totals": base / "totals_sample.csv",
        "portfolio_greeks_combos": base / "combos_sample.csv",
    }

    def _latest(name: str, fmt: str = "csv", outdir: str | None = None):
        return mapping.get(name)

    return _latest


def test_daily_report_full(monkeypatch, tmp_path):
    data_dir = Path(__file__).parent / "data"
    monkeypatch.setattr(
        "portfolio_exporter.core.io.latest_file", _fake_latest_factory(data_dir)
    )
    res = daily_report.main(["--json", "--output-dir", str(tmp_path)])
    assert res["sections"]["positions"] == 2
    assert res["sections"]["combos"] == 2
    assert res["sections"]["totals"] == 1
    assert (tmp_path / "daily_report.html").exists()
    assert (tmp_path / "daily_report.pdf").exists()
    # outputs list should contain both files
    outs = set(res["outputs"])
    assert any(str(p).endswith("daily_report.html") for p in outs)
    assert any(str(p).endswith("daily_report.pdf") for p in outs)


def test_daily_report_missing(monkeypatch, tmp_path):
    data_dir = Path(__file__).parent / "data"
    def _latest(name: str, fmt: str = "csv", outdir: str | None = None):
        mapping = {"portfolio_greeks_positions": data_dir / "positions_sample.csv"}
        return mapping.get(name)

    monkeypatch.setattr("portfolio_exporter.core.io.latest_file", _latest)
    res = daily_report.main(["--json", "--output-dir", str(tmp_path)])
    assert res["sections"]["positions"] == 2
    assert res["sections"]["combos"] == 0
    assert res["sections"]["totals"] == 0
    outs = set(res["outputs"])
    assert any(str(p).endswith("daily_report.html") for p in outs)
    assert any(str(p).endswith("daily_report.pdf") for p in outs)


def test_daily_report_json_only(monkeypatch, tmp_path):
    data_dir = Path(__file__).parent / "data"
    monkeypatch.setattr(
        "portfolio_exporter.core.io.latest_file", _fake_latest_factory(data_dir)
    )
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    res = daily_report.main(["--json"])
    assert res["sections"]["positions"] == 2
    assert res["outputs"] == []
    assert list(tmp_path.iterdir()) == []
