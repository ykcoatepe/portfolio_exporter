import importlib
import json
import sys
from io import StringIO
from pathlib import Path

import pytest

FIXTURES = Path("tests/data")

@pytest.mark.parametrize(
    "mod_path, argv, needs_env",
    [
        ("portfolio_exporter.scripts.daily_report", ["--json", "--no-files"], False),
        (
            "portfolio_exporter.scripts.net_liq_history_export",
            [
                "--json",
                "--no-files",
                "--source",
                "fixture",
                "--fixture-csv",
                str(FIXTURES / "net_liq_fixture.csv"),
            ],
            False,
        ),
        (
            "portfolio_exporter.scripts.quick_chain",
            ["--chain-csv", str(FIXTURES / "quick_chain_fixture.csv"), "--json"],
            False,
        ),
        (
            "portfolio_exporter.scripts.trades_report",
            ["--executions-csv", str(FIXTURES / "executions_fixture.csv"), "--json"],
            False,
        ),
        (
            "portfolio_exporter.scripts.portfolio_greeks",
            [
                "--positions-csv",
                str(FIXTURES / "positions_sample.csv"),
                "--json",
                "--no-files",
                "--combos-source",
                "engine",
            ],
            False,
        ),
        ("portfolio_exporter.scripts.doctor", ["--json", "--no-files"], True),
    ],
)
def test_entrypoint_main_ok(mod_path, argv, needs_env, monkeypatch, capsys, tmp_path):
    if needs_env:
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    mod = importlib.import_module(mod_path)
    result = mod.main(argv)
    out = capsys.readouterr().out
    if isinstance(result, dict):
        assert result.get("ok")
    else:
        data = json.loads(out.splitlines()[-1])
        assert data.get("ok")


def test_validate_json_entrypoint(monkeypatch):
    mod = importlib.import_module("portfolio_exporter.scripts.validate_json")
    sample = {
        "ok": True,
        "outputs": [],
        "warnings": [],
        "meta": {"schema_id": "report_summary", "schema_version": "1.0.0"},
        "sections": {},
    }
    monkeypatch.setattr(sys, "stdin", StringIO(json.dumps(sample)))
    assert mod.main([]) == 0
