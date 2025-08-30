import argparse
from pathlib import Path

from portfolio_exporter.scripts import daily_report, portfolio_greeks, doctor


def test_doctor_ok(monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", "tests/data")
    summary = doctor.cli(argparse.Namespace())  # type: ignore
    assert summary["ok"] is True


def test_doctor_header_fail(tmp_path, monkeypatch):
    csv = tmp_path / "portfolio_greeks_positions.csv"
    csv.write_text("underlying,qty\nAAPL,1\n")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    summary = doctor.cli(argparse.Namespace())  # type: ignore
    assert summary["ok"] is False


def test_daily_report_preflight(monkeypatch, tmp_path):
    samples = {
        "positions_sample.csv": "portfolio_greeks_positions.csv",
        "totals_sample.csv": "portfolio_greeks_totals.csv",
        "combos_sample.csv": "portfolio_greeks_combos.csv",
    }
    for src, dst in samples.items():
        (tmp_path / dst).write_text((Path("tests/data") / src).read_text())
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    res = daily_report.main(["--preflight", "--json", "--no-files"])
    assert res["ok"] is True


def test_daily_report_preflight_fail(tmp_path, monkeypatch):
    p = tmp_path / "portfolio_greeks_positions.csv"
    p.write_text("underlying,qty\nAAPL,1\n")
    (tmp_path / "portfolio_greeks_totals.csv").write_text("account,net_liq\nA,1\n")
    (tmp_path / "portfolio_greeks_combos.csv").write_text("underlying\nAAPL\n")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    res = daily_report.main(["--preflight", "--json", "--no-files"])
    assert res["ok"] is False


def test_portfolio_greeks_preflight(monkeypatch):
    res = portfolio_greeks.main([
        "--positions-csv",
        "tests/data/positions_sample.csv",
        "--json",
        "--no-files",
        "--preflight",
    ])
    assert res["ok"] is True


def test_portfolio_greeks_preflight_fail(tmp_path):
    bad = tmp_path / "pos.csv"
    bad.write_text("underlying,qty\nAAPL,1\n")
    res = portfolio_greeks.main([
        "--positions-csv",
        str(bad),
        "--json",
        "--no-files",
        "--preflight",
    ])
    assert res["ok"] is False
