import json
import re
import subprocess
import sys
from pathlib import Path


def test_manifest_written_quick_chain(tmp_path):
    env = {"PYTHONPATH": ".", "PE_TEST_MODE": "1"}
    cmd = [
        sys.executable,
        "portfolio_exporter/scripts/quick_chain.py",
        "--chain-csv",
        "tests/data/quick_chain_fixture.csv",
        "--output-dir",
        str(tmp_path),
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
    data = json.loads(result.stdout.splitlines()[-1])
    manifest_path = tmp_path / "quick_chain_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["outputs"]
    first = manifest["outputs"][0]
    assert re.fullmatch(r"[0-9a-f]{64}", first["sha256"])
    assert first["bytes"] > 0
    assert str(manifest_path) in data["outputs"]


def test_no_manifest_json_only_daily_report(monkeypatch):
    env = {"PYTHONPATH": ".", "OUTPUT_DIR": "tests/data"}
    cmd = [
        sys.executable,
        "portfolio_exporter/scripts/daily_report.py",
        "--json",
        "--no-files",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
    data = json.loads(result.stdout.splitlines()[-1])
    assert data["outputs"] == []
    assert not Path("tests/data/daily_report_manifest.json").exists()
    assert not Path("daily_report_manifest.json").exists()
