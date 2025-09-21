import pytest

from portfolio_exporter.scripts import trades_report


def _make_exec_csv(tmp_path):
    path = tmp_path / "exec.csv"
    path.write_text(
        (
            "exec_id,perm_id,order_id,symbol,secType,Side,qty,price,datetime,expiry,right,strike\n"
            "1,1,1,AAPL,OPT,BOT,1,1.0,2024-01-01T10:00:00,2024-02-16,C,150\n"
        )
    )
    return path


def test_excel_written_when_openpyxl_present(tmp_path):
    pytest.importorskip("openpyxl")
    exec_csv = _make_exec_csv(tmp_path)
    summary = trades_report.main(
        [
            "--executions-csv",
            str(exec_csv),
            "--output-dir",
            str(tmp_path),
            "--excel",
        ]
    )
    xlsx_path = tmp_path / "trades_report.xlsx"
    assert xlsx_path.exists()
    assert summary["ok"] is True
    assert summary.get("meta", {}).get("outputs", {}).get("trades_report_xlsx") == str(xlsx_path)


def test_excel_missing_module(monkeypatch, tmp_path, capsys):
    import builtins as _builtins

    orig_import = _builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openpyxl":
            raise ModuleNotFoundError
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(_builtins, "__import__", fake_import)
    exec_csv = _make_exec_csv(tmp_path)
    summary = trades_report.main(
        [
            "--executions-csv",
            str(exec_csv),
            "--output-dir",
            str(tmp_path),
            "--excel",
        ]
    )
    xlsx_path = tmp_path / "trades_report.xlsx"
    assert not xlsx_path.exists()
    err = capsys.readouterr().err
    assert "openpyxl" in err
    assert summary["ok"] is True


def test_json_only_unaffected(tmp_path):
    exec_csv = _make_exec_csv(tmp_path)
    summary = trades_report.main(
        [
            "--executions-csv",
            str(exec_csv),
            "--output-dir",
            str(tmp_path),
            "--json",
            "--no-files",
        ]
    )
    assert summary["outputs"] == []
    assert not (tmp_path / "trades_report.xlsx").exists()
