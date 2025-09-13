import json

from portfolio_exporter.scripts import daily_report, net_liq_history_export, validate_json


def test_daily_report_schema(monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", "tests/data")
    res = daily_report.main(["--json", "--no-files"])
    validate_json.validate(res)


def test_net_liq_schema(monkeypatch, capsys):
    net_liq_history_export.main([
        "--json",
        "--no-files",
        "--source",
        "fixture",
        "--fixture-csv",
        "tests/data/net_liq_fixture.csv",
    ])
    data = json.loads(capsys.readouterr().out)
    validate_json.validate(data)
