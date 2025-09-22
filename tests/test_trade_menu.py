import types, importlib, builtins, main

import pandas as pd


def test_trade_menu_dispatch(monkeypatch):
    called = []
    monkeypatch.setattr(
        "portfolio_exporter.scripts.trades_report.run",
        lambda fmt="csv", **_: called.append(fmt),
    )
    monkeypatch.setattr(
        "portfolio_exporter.scripts.trades_report._load_trades",
        lambda: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "portfolio_exporter.scripts.trades_report._load_open_orders",
        lambda: pd.DataFrame(),
    )
    importlib.reload(main)
    inp = iter(["3", "e", "r", "0"])
    mock_input = lambda _="": next(inp, "0")
    monkeypatch.setattr(builtins, "input", mock_input)
    monkeypatch.setattr(main, "input", mock_input)
    main.parse_args = lambda: types.SimpleNamespace(
        quiet=True,
        format="excel",
        list_tasks=False,
        workflow=None,
        tasks=None,
        tasks_csv=None,
        dry_run=False,
        json=False,
    )
    main.main()
    assert "excel" in called
