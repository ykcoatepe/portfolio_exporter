import json
import os
import subprocess
import sys
from pathlib import Path

DB_PATH = Path("tmp_test_run/combos.db")


def _run(args, tmp_path):
    env = os.environ.copy()
    env.update({"PYTHONPATH": ".", "PE_TEST_MODE": "1", "PE_OUTPUT_DIR": str(tmp_path)})
    if DB_PATH.exists():
        DB_PATH.unlink()
    return subprocess.run(
        [sys.executable, "-m", "portfolio_exporter.scripts.combo_db_maint", *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )


def test_json_only(tmp_path):
    result = _run(["--json", "--no-files"], tmp_path)
    data = json.loads(result.stdout)
    assert data["ok"]
    assert set(data["sections"]).issuperset({"broken", "repairable"})
    assert data["outputs"] == []


def test_fix_writes_files(tmp_path):
    result = _run(["--fix", "--output-dir", str(tmp_path), "--json", "--debug-timings"], tmp_path)
    data = json.loads(result.stdout)
    assert (tmp_path / "combo_db_before.csv").exists()
    assert (tmp_path / "combo_db_after.csv").exists()
    assert (tmp_path / "combo_db_maint_manifest.json").exists()
    assert (tmp_path / "timings.csv").exists()
    assert data["ok"]


def test_idempotent(tmp_path):
    _run(["--fix", "--output-dir", str(tmp_path), "--json"], tmp_path)
    result = _run(["--json", "--no-files"], tmp_path)
    data = json.loads(result.stdout)
    assert data["sections"]["broken"] == 0
