import types, importlib, builtins, main


def test_trade_menu_dispatch(monkeypatch):
    called = []
    monkeypatch.setattr(
        "portfolio_exporter.scripts.trades_report.run",
        lambda fmt="csv": called.append(fmt),
    )
    importlib.reload(main)
    inp = iter(["3", "e", "r", "0"])
    monkeypatch.setattr(builtins, "input", lambda _="": next(inp))
    main.parse_args = lambda: types.SimpleNamespace(quiet=True, format="excel")
    main.main()
    assert "excel" in called
