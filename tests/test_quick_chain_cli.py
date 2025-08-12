import json
import os
import subprocess
import sys
import importlib


def test_json_summary_no_files(tmp_path):
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": ".",
        "PE_TEST_MODE": "1",
        "PE_OUTPUT_DIR": str(tmp_path),
    })
    result = subprocess.run(
        [
            sys.executable,
            "portfolio_exporter/scripts/quick_chain.py",
            "--chain-csv",
            "tests/data/quick_chain_fixture.csv",
            "--no-pretty",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    data = json.loads(result.stdout)
    assert data["rows"] > 0
    assert data["underlyings"]
    assert not any(tmp_path.iterdir())


def test_output_dir_override(tmp_path):
    env = os.environ.copy()
    env.update({"PYTHONPATH": ".", "PE_TEST_MODE": "1"})
    subprocess.run(
        [
            sys.executable,
            "portfolio_exporter/scripts/quick_chain.py",
            "--chain-csv",
            "tests/data/quick_chain_fixture.csv",
            "--output-dir",
            str(tmp_path),
        ],
        check=True,
        env=env,
    )
    assert (tmp_path / "quick_chain.csv").exists()


def test_lazy_deps(monkeypatch, tmp_path, capsys):
    monkeypatch.setitem(sys.modules, "ib_insync", None)
    monkeypatch.setenv("PE_TEST_MODE", "1")
    monkeypatch.setenv("PE_OUTPUT_DIR", str(tmp_path))
    if "portfolio_exporter.scripts.quick_chain" in sys.modules:
        del sys.modules["portfolio_exporter.scripts.quick_chain"]
    qc = importlib.import_module("portfolio_exporter.scripts.quick_chain")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quick_chain",
            "--chain-csv",
            "tests/data/quick_chain_fixture.csv",
            "--json",
        ],
    )
    code = qc._run_cli_v3()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 0
    assert data["rows"] > 0
    assert not any(tmp_path.iterdir())
