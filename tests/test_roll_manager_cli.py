import argparse
import types
import argparse
import types
import importlib.util
import pathlib
import pandas as pd

spec = importlib.util.spec_from_file_location(
    "roll_manager",
    pathlib.Path(__file__).resolve().parents[1]
    / "portfolio_exporter/scripts/roll_manager.py",
)
roll_manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roll_manager)


def _stub_positions():
    return pd.DataFrame()


def _stub_spinner(msg, fn, *a, **k):
    return fn(*a, **k)


def test_run_returns_df(monkeypatch):
    fake_pg = types.SimpleNamespace(_load_positions=_stub_positions)
    monkeypatch.setattr(roll_manager, "portfolio_greeks", fake_pg)
    monkeypatch.setattr(roll_manager, "run_with_spinner", _stub_spinner)
    df = roll_manager.run(return_df=True)
    assert isinstance(df, pd.DataFrame)


def test_cli_json(monkeypatch):
    fake_pg = types.SimpleNamespace(_load_positions=_stub_positions)
    monkeypatch.setattr(roll_manager, "portfolio_greeks", fake_pg)
    monkeypatch.setattr(roll_manager, "run_with_spinner", _stub_spinner)
    ns = argparse.Namespace(
        include_cal=False,
        days=7,
        tenor="all",
        no_pretty=True,
        json=True,
        output_dir=None,
    )
    summary = roll_manager.cli(ns)
    for key in ["n_candidates", "n_selected", "underlyings", "by_structure", "outputs"]:
        assert key in summary
