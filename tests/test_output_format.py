import types
import pandas as pd
import importlib
import main

from portfolio_exporter.menus import pre


def test_output_format_toggle(monkeypatch, tmp_path):
    # patch io.save to capture fmt
    seen = {}

    def fake_save(df, name, fmt="csv", outdir=None):
        seen["fmt"] = fmt

    monkeypatch.setattr("portfolio_exporter.core.io.save", fake_save)
    # monkeypatch one exporter to return a dummy DF
    monkeypatch.setattr(
        "portfolio_exporter.scripts.historic_prices.run",
        lambda fmt="csv": fake_save(pd.DataFrame({"a": [1]}), "historic", fmt),
    )
    # simulate menu input: toggle (f), then run historic (h), then return (r)
    inputs = iter(["f", "h", "r"])
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    status = types.SimpleNamespace(update=lambda *a, **k: None, console=main.console)
    pre.launch(status, "csv")
    assert seen.get("fmt") == "excel"  # csv -> excel after one toggle
