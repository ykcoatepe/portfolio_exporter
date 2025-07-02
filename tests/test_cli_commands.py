import os
import sys
import subprocess
from pathlib import Path

import pandas as pd
import pytest
from ib_insync import Option

COMMANDS = [
    ["pulse", "--tickers", "AAPL"],
    ["live", "--tickers", "AAPL"],
    ["options", "--tickers", "AAPL", "--expiries", "20250101"],
    ["positions"],
    ["report", "--input", "sample_trades.csv", "--date", "today", "--format", "pdf"],
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


def test_live_quiet(tmp_path):
    env = os.environ.copy()
    env["PE_TEST_MODE"] = "1"
    env["OUTPUT_DIR"] = str(tmp_path)
    cmd = [
        sys.executable,
        "main.py",
        "--output-dir",
        str(tmp_path),
        "live",
        "--tickers",
        "AAPL",
        "--quiet",
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    csv = next(tmp_path.glob("*.csv"))
    df = pd.read_csv(csv)
    assert list(df.columns) == ["ticker", "price", "bid", "ask", "source"]
    assert len(df) == 1


def test_live_interactive_quiet(tmp_path, monkeypatch):
    import shutil
    shutil.copyfile("main.py", tmp_path / "main.py")
    shutil.copyfile("trades_report.py", tmp_path / "trades_report.py")
    shutil.copyfile("sample_trades.csv", tmp_path / "sample_trades.csv")
    shutil.copytree("src", tmp_path / "src")
    shutil.copytree("utils", tmp_path / "utils")
    # Copy other necessary files for main.py to run
    shutil.copyfile("net_liq_history_export.py", tmp_path / "net_liq_history_export.py")
    shutil.copyfile("option_chain_snapshot.py", tmp_path / "option_chain_snapshot.py")
    shutil.copyfile("orchestrate_dataset.py", tmp_path / "orchestrate_dataset.py")
    shutil.copyfile("tech_signals_ibkr.py", tmp_path / "tech_signals_ibkr.py")
    shutil.copyfile("update_tickers.py", tmp_path / "update_tickers.py")

    # Mock input for interactive mode
    inputs = iter(["2", "y", "AAPL", "", "8"])  # Select live, quiet=y, ticker, default output, exit
    monkeypatch.setattr('builtins.input', lambda _: next(inputs))

    # Mock argparse.Namespace for cmd_live
    class MockArgs:
        def __init__(self):
            self.tickers = ""
            self.output = ""
            self.format = "csv"
            self.quiet = False

    mock_args = MockArgs()
    monkeypatch.setattr('argparse.Namespace', MockArgs)

    # Temporarily change current working directory for the test
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    sys.path.insert(0, str(tmp_path))
    try:
        # Call main directly
        from main import main as main_app
        main_app()
    finally:
        os.chdir(original_cwd)
        sys.path.remove(str(tmp_path))

    # Assert that the output file is created
    output_files = list(tmp_path.glob("live_quotes_*.csv"))
    assert len(output_files) == 1
    df = pd.read_csv(output_files[0])
    assert not df.empty
    assert "AAPL" in df["ticker"].values
