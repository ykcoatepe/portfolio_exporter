import argparse

from portfolio_exporter.scripts import doctor
from portfolio_exporter.core import schemas as pa_schemas
from portfolio_exporter.core import io as core_io


def test_missing_output_dir(monkeypatch):
    monkeypatch.delenv("OUTPUT_DIR", raising=False)
    monkeypatch.setenv("CP_REFRESH_TOKEN", "x")
    monkeypatch.setenv("TWS_EXPORT_DIR", "/tmp")
    summary = doctor.cli(argparse.Namespace())
    fixes = summary["sections"]["fixes"]
    assert any("mkdir -p" in f for f in fixes)


def test_missing_cp_refresh_token(monkeypatch, tmp_path):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("CP_REFRESH_TOKEN", raising=False)
    monkeypatch.setenv("TWS_EXPORT_DIR", "/tmp")
    summary = doctor.cli(argparse.Namespace())
    fixes = summary["sections"]["fixes"]
    assert any("CP_REFRESH_TOKEN" in f for f in fixes)


def test_missing_pandera(monkeypatch, tmp_path):
    csv = tmp_path / "portfolio_greeks_positions.csv"
    csv.write_text("underlying,qty\nAAPL,1\n")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CP_REFRESH_TOKEN", "x")
    monkeypatch.setenv("TWS_EXPORT_DIR", "/tmp")

    def fake_latest(name, fmt="csv", outdir=None):
        return csv if name == "portfolio_greeks_positions" else None

    monkeypatch.setattr(core_io, "latest_file", fake_latest)
    monkeypatch.setattr(pa_schemas, "check_headers", lambda n, df: ["pandera not installed"])

    summary = doctor.cli(argparse.Namespace())
    fixes = summary["sections"]["fixes"]
    assert any("pip install pandera" in f for f in fixes)
