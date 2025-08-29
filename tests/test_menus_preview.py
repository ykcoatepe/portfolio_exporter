import types
import importlib.util
import pathlib
import sys
import types
import main

# stub optional dependencies for import-time side effects
sys.modules.setdefault("prompt_toolkit", types.SimpleNamespace(prompt=lambda *a, **k: ""))
sys.modules.setdefault("dateparser", types.SimpleNamespace(parse=lambda *a, **k: None))
sys.modules.setdefault(
    "ib_insync",
    types.SimpleNamespace(IB=object, Option=object, Stock=object),
)

spec = importlib.util.spec_from_file_location(
    "trade", pathlib.Path("portfolio_exporter/menus/trade.py")
)
trade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trade)


def test_preview_daily_report(monkeypatch, capsys):
    summary = {
        "sections": {"positions": 1, "combos": 2, "totals": 3},
        "expiry_radar": {"window_days": 5, "basis": "positions", "rows": []},
    }

    def fake_main(args=None):
        assert args == ["--json", "--no-files"]
        return summary

    monkeypatch.setattr("portfolio_exporter.scripts.daily_report.main", fake_main)

    inputs = iter(["p", "r"])
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    status = types.SimpleNamespace(update=lambda *a, **k: None, console=main.console)

    trade.launch(status, "csv")

    out = capsys.readouterr().out
    assert "Positions: 1" in out
    assert "Combos: 2" in out
    assert "Totals: 3" in out
    assert "Expiry radar" in out


def test_preview_roll_manager(monkeypatch, capsys):
    summary = {
        "sections": {"candidates": 4},
        "candidates": [
            {"underlying": "AAA", "delta": 0.1, "debit_credit": 0.5},
            {"underlying": "BBB", "delta": -0.8, "debit_credit": -0.3},
            {"underlying": "CCC", "delta": 0.5, "debit_credit": 0.1},
            {"underlying": "DDD", "delta": 1.2, "debit_credit": 0.2},
        ],
    }

    def fake_cli(args=None):
        assert args == ["--dry-run", "--json", "--no-files"]
        return summary

    monkeypatch.setattr("portfolio_exporter.scripts.roll_manager.cli", fake_cli)

    inputs = iter(["v", "r"])
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    status = types.SimpleNamespace(update=lambda *a, **k: None, console=main.console)

    trade.launch(status, "csv")

    out = capsys.readouterr().out
    assert "Candidates: 4" in out
    # Sorted by absolute delta: DDD (1.2), BBB (0.8), CCC (0.5)
    assert "DDD Δ+1.20 +0.20" in out
    assert "BBB Δ-0.80 -0.30" in out
    assert "CCC Δ+0.50 +0.10" in out
