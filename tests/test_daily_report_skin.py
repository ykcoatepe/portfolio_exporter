from pathlib import Path

from bs4 import BeautifulSoup

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


def test_json_only_unaffected(monkeypatch, tmp_path):
    data_dir = Path(__file__).parent / "data"
    monkeypatch.setattr(
        "portfolio_exporter.core.io.latest_file", _fake_latest_factory(data_dir)
    )
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    res = daily_report.main(["--json"])
    assert res["sections"]["positions"] == 2
    assert res["outputs"] == []


def test_html_dom_snapshot(monkeypatch, tmp_path):
    data_dir = Path(__file__).parent / "data"
    monkeypatch.setattr(
        "portfolio_exporter.core.io.latest_file", _fake_latest_factory(data_dir)
    )
    daily_report.main(["--output-dir", str(tmp_path)])
    html = (tmp_path / "daily_report.html").read_text()
    soup = BeautifulSoup(html, "html.parser")
    lines = [
        line
        for line in soup.get_text("\n").splitlines()
        if line and not line.startswith("Generated:") and not line.startswith("Output dir:")
    ]
    text = "\n".join(lines)
    expected = (Path(__file__).parent / "data" / "daily_report_dom.txt").read_text()
    assert text.strip() == expected.strip()
    headers = [h.get_text() for h in soup.find_all("h2")]
    for header in ["Delta Buckets", "Theta Decay 5d", "Totals", "Combos", "Positions"]:
        assert header in headers
    tables = soup.find_all("table")
    th_text = {th.get_text() for tab in tables for th in tab.find_all("th")}
    for col in ["underlying", "right", "qty", "structure"]:
        assert col in th_text
