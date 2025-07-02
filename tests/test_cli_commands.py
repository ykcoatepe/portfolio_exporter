import os
import sys
import subprocess
from pathlib import Path
import pytest

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
        [sys.executable, "main.py", "--output-dir", str(tmp_path)],
        input="8\n",
        text=True,
        capture_output=True,
        env=env,
    )
    assert proc.returncode == 0
