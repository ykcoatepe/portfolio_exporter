import os
import sys
import subprocess
from pathlib import Path
import pytest
from ib_insync import Option

COMMANDS = [
    ["pulse", "--tickers", "AAPL"],
    ["live", "--tickers", "AAPL", "--format", "pdf"],
    ["options", "--tickers", "AAPL", "--expiries", "20250101"],
    ["positions"],
    ["report", "--input", "sample_trades.csv", "--format", "pdf"],
    ["portfolio-greeks"],
    ["orchestrate"],
]


@pytest.mark.parametrize("args", COMMANDS)
def test_cli_command(args, tmp_path):
    env = os.environ.copy()
    env["PE_TEST_MODE"] = "1"
    env["OUTPUT_DIR"] = str(tmp_path)
    cmd = [sys.executable, "main.py", "--output-dir", str(tmp_path), *args]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert any(tmp_path.iterdir())


def test_interactive_exit(tmp_path):
    env = os.environ.copy()
    env["PE_TEST_MODE"] = "1"
    env["OUTPUT_DIR"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, "main.py"],
        input=b"8\n",
        capture_output=True,
        env=env,
    )
    assert proc.returncode == 0


def test_interactive_portfolio_greeks(tmp_path):
    env = os.environ.copy()
    env["PE_TEST_MODE"] = "1"
    env["OUTPUT_DIR"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, "main.py"],
        input=b"6\nn\n8\n",
        capture_output=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    print(f"STDOUT: {proc.stdout}")
    print(f"STDERR: {proc.stderr}")
    # Assert that a portfolio_greeks CSV is produced
    assert any(
        f.name.startswith("portfolio_greeks") and f.suffix == ".csv"
        for f in tmp_path.iterdir()
    )
