import json
import subprocess
import sys
from pathlib import Path


def _write_fixture(tmp_path: Path) -> None:
    (tmp_path / "trades_report_20250101.csv").write_text(
        "cluster_id,structure,pnl\n1,call,100\n2,put,-50\n3,call,25\n"
    )


def test_json_only(tmp_path):
    _write_fixture(tmp_path)
    env = {
        "PYTHONPATH": ".",
        "PE_TEST_MODE": "1",
        "PE_OUTPUT_DIR": str(tmp_path),
    }
    result = subprocess.run(
        [
            sys.executable,
            "portfolio_exporter/scripts/trades_dashboard.py",
            "--json",
            "--no-files",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    data = json.loads(result.stdout.splitlines()[-1])
    assert data["ok"] is True
    for key in ["clusters", "net_credit_debit", "by_structure", "top_clusters"]:
        assert key in data["sections"]
    assert data["outputs"] == []


def test_output_dir(tmp_path):
    _write_fixture(tmp_path)
    outdir = tmp_path / "dash"
    env = {
        "PYTHONPATH": ".",
        "PE_TEST_MODE": "1",
        "PE_OUTPUT_DIR": str(tmp_path),
    }
    result = subprocess.run(
        [
            sys.executable,
            "portfolio_exporter/scripts/trades_dashboard.py",
            "--json",
            "--output-dir",
            str(outdir),
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    data = json.loads(result.stdout.splitlines()[-1])
    html_path = outdir / "trades_dashboard.html"
    manifest_path = outdir / "trades_dashboard_manifest.json"
    assert html_path.exists()
    assert manifest_path.exists()
    assert str(html_path) in data["outputs"]
    assert str(manifest_path) in data["outputs"]
