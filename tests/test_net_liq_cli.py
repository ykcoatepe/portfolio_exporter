import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest


def _run_cli(args, env):
    result = subprocess.run(
        [sys.executable, "-m", "portfolio_exporter.scripts.net_liq_history_export", *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return result.stdout


def _have_reportlab() -> bool:
    try:
        import reportlab  # noqa: F401
    except Exception:
        return False
    return True


def test_json_no_write(tmp_path):
    env = os.environ.copy()
    env.update({"PYTHONPATH": ".", "PE_TEST_MODE": "1", "PE_OUTPUT_DIR": str(tmp_path)})
    out = _run_cli(
        [
            "--source",
            "fixture",
            "--fixture-csv",
            "tests/data/net_liq_fixture.csv",
            "--json",
            "--quiet",
        ],
        env,
    )
    data = json.loads(out)
    assert data["rows"] == 10
    assert data["start"] == "2024-01-02"
    assert data["end"] == "2024-01-16"
    assert data["outputs"] == {"csv": "", "excel": "", "pdf": ""}
    assert not any(tmp_path.iterdir())


@pytest.mark.skipif(not _have_reportlab(), reason="reportlab not installed")
def test_file_writes(tmp_path):
    env = os.environ.copy()
    env.update({"PYTHONPATH": ".", "PE_TEST_MODE": "1"})
    outdir = tmp_path / ".tmp_nlh"
    out = _run_cli(
        [
            "--source",
            "fixture",
            "--fixture-csv",
            "tests/data/net_liq_fixture.csv",
            "--json",
            "--output-dir",
            str(outdir),
            "--csv",
            "--pdf",
            "--quiet",
        ],
        env,
    )
    data = json.loads(out)
    csv_path = Path(data["outputs"]["csv"])
    pdf_path = Path(data["outputs"]["pdf"])
    assert csv_path.exists()
    assert pdf_path.exists()
    df = pd.read_csv(csv_path)
    assert list(df.columns) == ["date", "NetLiq"]
    assert len(df) == 10


def test_date_filter(tmp_path):
    env = os.environ.copy()
    env.update({"PYTHONPATH": ".", "PE_TEST_MODE": "1", "PE_OUTPUT_DIR": str(tmp_path)})
    out = _run_cli(
        [
            "--source",
            "fixture",
            "--fixture-csv",
            "tests/data/net_liq_fixture.csv",
            "--start",
            "2024-01-03",
            "--end",
            "2024-01-05",
            "--json",
        ],
        env,
    )
    data = json.loads(out)
    assert data["rows"] == 3
    assert data["start"] == "2024-01-03"
    assert data["end"] == "2024-01-05"


def test_quiet_suppresses_table(tmp_path):
    env = os.environ.copy()
    env.update({"PYTHONPATH": ".", "PE_TEST_MODE": "1", "PE_OUTPUT_DIR": str(tmp_path)})
    loud = _run_cli(
        [
            "--source",
            "fixture",
            "--fixture-csv",
            "tests/data/net_liq_fixture.csv",
        ],
        env,
    )
    assert "NetLiq" in loud
    quiet = _run_cli(
        [
            "--source",
            "fixture",
            "--fixture-csv",
            "tests/data/net_liq_fixture.csv",
            "--quiet",
        ],
        env,
    )
    assert quiet.strip() == ""

