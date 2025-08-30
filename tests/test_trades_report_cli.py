import json
import subprocess
import sys

def _make_exec_csv(tmp_path):
    path = tmp_path / "exec.csv"
    path.write_text(
        "exec_id,perm_id,order_id,symbol,secType,Side,qty,price,datetime,Liquidation,lastLiquidity,OrderRef\n"
        "1,1,1,AAPL,STK,BOT,1,10.0,2024-01-01T10:00:00,0,1,\n"
    )
    return path


def test_json_only_outputs_empty(tmp_path):
    exec_csv = _make_exec_csv(tmp_path)
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
            str(exec_csv),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    data = json.loads(result.stdout.splitlines()[-1])
    assert data["outputs"] == []
    assert not list(tmp_path.glob("trades_report*.csv"))


def test_output_dir_writes_csv(tmp_path):
    exec_csv = _make_exec_csv(tmp_path)
    env = {"PYTHONPATH": ".", "PE_TEST_MODE": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "portfolio_exporter/scripts/trades_report.py",
            "--executions-csv",
            str(exec_csv),
            "--output-dir",
            str(tmp_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    data = json.loads(result.stdout.splitlines()[-1])
    report_files = list(tmp_path.glob("trades_report*.csv"))
    assert report_files
    assert str(report_files[0]) in data["outputs"]
