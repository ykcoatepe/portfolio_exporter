import builtins
import importlib.util
import types
import sys
from pathlib import Path

# stub core.ui to avoid heavy imports
fake_ui = types.SimpleNamespace(prompt_input=lambda prompt="": "")
sys.modules["portfolio_exporter.core.ui"] = fake_ui

spec = importlib.util.spec_from_file_location(
    "portfolio_exporter.menus.trade", Path("portfolio_exporter/menus/trade.py")
)
trade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trade)  # type: ignore[arg-type]


def run_menu(monkeypatch, choice: str) -> str:
    monkeypatch.setattr(trade, "prompt_input", lambda prompt="": choice)
    monkeypatch.setattr(builtins, "input", lambda prompt="": choice)
    trade.launch(status=None, default_fmt="csv")
    return ""


def test_preview_roll_manager(monkeypatch, capsys):
    def fake_rm_main(argv):
        assert argv == ["--dry-run", "--json", "--no-files"]
        return {
            "candidates": [
                {"underlying": "A", "delta": 1.0, "debit_credit": 0.1},
                {"underlying": "B", "delta": -0.5, "debit_credit": 0.2},
                {"underlying": "C", "delta": 0.2, "debit_credit": -0.3},
                {"underlying": "D", "delta": 0.8, "debit_credit": 0.4},
            ]
        }

    fake_rm = types.SimpleNamespace(main=fake_rm_main, cli=fake_rm_main)
    sys.modules["portfolio_exporter.scripts.roll_manager"] = fake_rm
    run_menu(monkeypatch, "v r")
    out = capsys.readouterr().out
    assert "Candidates: 4" in out
    assert "A Δ+1.00 +0.10" in out
    assert "D Δ+0.80 +0.40" in out
    assert "B Δ-0.50 +0.20" in out


def test_preflight_daily_report_warns(monkeypatch, capsys):
    def fake_daily_main(argv):
        assert argv == ["--preflight", "--json", "--no-files"]
        return {"warnings": ["run: portfolio-greeks"]}

    fake_daily = types.SimpleNamespace(main=fake_daily_main)
    sys.modules["portfolio_exporter.scripts.daily_report"] = fake_daily
    run_menu(monkeypatch, "f r")
    out = capsys.readouterr().out
    assert "run: portfolio-greeks" in out


def test_preflight_roll_manager_missing_positions(monkeypatch, capsys):
    fake_io = types.SimpleNamespace(latest_file=lambda name: None)
    sys.modules["portfolio_exporter.core.io"] = fake_io
    run_menu(monkeypatch, "x r")
    out = capsys.readouterr().out
    assert "run: portfolio-greeks" in out
