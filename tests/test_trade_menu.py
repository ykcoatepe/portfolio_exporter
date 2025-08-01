import types, importlib, builtins, main


def test_trade_menu_dispatch(monkeypatch):
    called = []
    monkeypatch.setattr(
        "portfolio_exporter.scripts.trades_report.run",
        lambda fmt="csv", **_: called.append(fmt),
    )
    importlib.reload(main)
    inp = iter(["3", "e", "r", "0"])
    mock_input = lambda _="": next(inp)
    monkeypatch.setattr(builtins, "input", mock_input)
    monkeypatch.setattr(main, "input", mock_input)
    main.parse_args = lambda: types.SimpleNamespace(quiet=True, format="excel")
    main.main()
    assert "excel" in called
