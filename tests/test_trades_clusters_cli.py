import json
import subprocess
import sys


def test_clusters_json_only(tmp_path):
    env = {
        "PYTHONPATH": ".",
        "PE_TEST_MODE": "1",
        "PE_OUTPUT_DIR": str(tmp_path),
    }
    result = subprocess.run(
        [
            sys.executable,
            "portfolio_exporter/scripts/trades_report.py",
            "--executions-csv",
            "tests/data/executions_fixture.csv",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    data = json.loads(result.stdout.splitlines()[-1])
    assert data["outputs"] == []
    assert data["sections"]["clusters"] == 1
    assert data["sections"]["combos"] == 0
    assert not list(tmp_path.glob("trades_clusters*.csv"))


def test_clusters_output_dir(tmp_path):
    outdir = tmp_path / ".tmp_trades"
    env = {"PYTHONPATH": ".", "PE_TEST_MODE": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "portfolio_exporter/scripts/trades_report.py",
            "--executions-csv",
            "tests/data/executions_fixture.csv",
            "--output-dir",
            str(outdir),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    data = json.loads(result.stdout.splitlines()[-1])
    clusters_path = outdir / "trades_clusters.csv"
    manifest_path = outdir / "trades_report_manifest.json"
    assert clusters_path.exists()
    assert manifest_path.exists()
    assert str(clusters_path) in data["outputs"]
    assert str(manifest_path) in data["outputs"]
