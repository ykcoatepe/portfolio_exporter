import json
from pathlib import Path

from portfolio_exporter.scripts.micro_momo_analyzer import main as mm_main


def test_symbols_csv_only_json_no_files(tmp_path, capsys):
    out = tmp_path / "out"
    out.mkdir()
    # run with two symbols, csv-only, no files, JSON to stdout
    rc = mm_main([
        "--symbols",
        "AAA,BBB",
        "--cfg",
        "tests/data/micro_momo_config.json",
        "--out_dir",
        str(out),
        "--data-mode",
        "csv-only",
        "--json",
        "--no-files",
    ])
    assert rc == 0
    out_json = capsys.readouterr().out.strip()
    assert out_json, "expected JSON output"
    arr = json.loads(out_json)
    syms = {row["symbol"] for row in arr}
    assert syms == {"AAA", "BBB"}

