import json
import subprocess
import json
import subprocess
import sys


def _make_condor_exec_csv(tmp_path):
    path = tmp_path / "condor.csv"
    path.write_text(
        "exec_id,perm_id,order_id,symbol,secType,Side,qty,price,datetime,expiry,right,strike\n"
        "1,1,1,AAPL,OPT,BOT,1,1.0,2024-01-01T10:00:00,2024-02-16,P,90\n"
        "2,1,2,AAPL,OPT,SLD,1,2.0,2024-01-01T10:00:01,2024-02-16,P,95\n"
        "3,1,3,AAPL,OPT,SLD,1,2.0,2024-01-01T10:00:02,2024-02-16,C,105\n"
        "4,1,4,AAPL,OPT,BOT,1,1.0,2024-01-01T10:00:03,2024-02-16,C,110\n"
    )
    return path


def test_json_only_filters(tmp_path):
    env = {"PYTHONPATH": ".", "PE_TEST_MODE": "1", "PE_OUTPUT_DIR": str(tmp_path)}
    result = subprocess.run(
        [
            sys.executable,
            "portfolio_exporter/scripts/trades_report.py",
            "--executions-csv",
            "tests/data/executions_fixture.csv",
            "--symbol",
            "AAPL",
            "--effect-in",
            "Close",
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
    assert data["sections"]["filtered"]["rows_count"] >= 0


def test_filtered_files_written(tmp_path):
    exec_csv = _make_condor_exec_csv(tmp_path)
    outdir = tmp_path / ".tmp_trf"
    env = {"PYTHONPATH": ".", "PE_TEST_MODE": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "portfolio_exporter/scripts/trades_report.py",
            "--executions-csv",
            str(exec_csv),
            "--structure-in",
            "condor",
            "--top-n",
            "5",
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
    filtered_rows = outdir / "trades_report_filtered.csv"
    filtered_clusters = outdir / "trades_clusters_filtered.csv"
    manifest = outdir / "trades_report_manifest.json"
    assert filtered_rows.exists()
    assert filtered_clusters.exists()
    assert manifest.exists()
    assert str(filtered_rows) in data["outputs"]
    assert str(filtered_clusters) in data["outputs"]
    assert str(manifest) in data["outputs"]
