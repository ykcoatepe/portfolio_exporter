import json
import os
import subprocess
import sys


def test_json_only_outputs_empty(tmp_path):
    env = {
        "PYTHONPATH": ".",
        "PE_TEST_MODE": "1",
        "PE_OUTPUT_DIR": str(tmp_path),
    }
    result = subprocess.run(
        [
            sys.executable,
            "portfolio_exporter/scripts/portfolio_greeks.py",
            "--positions-csv",
            "tests/data/positions_sample.csv",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    data = json.loads(result.stdout.splitlines()[-1])
    assert data["outputs"] == []
    assert not any(tmp_path.iterdir())


def test_output_dir_writes_csvs(tmp_path):
    env = {"PYTHONPATH": ".", "PE_TEST_MODE": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "portfolio_exporter/scripts/portfolio_greeks.py",
            "--positions-csv",
            "tests/data/positions_sample.csv",
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
    for name in [
        "portfolio_greeks_positions.csv",
        "portfolio_greeks_totals.csv",
        "portfolio_greeks_combos.csv",
    ]:
        p = tmp_path / name
        assert p.exists()
        assert str(p) in data["outputs"]
