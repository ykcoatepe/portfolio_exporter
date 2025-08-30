import builtins, types, importlib, main


def test_user_tech_signals(monkeypatch):
    called = {}
    monkeypatch.setattr(
        "portfolio_exporter.scripts.tech_signals_ibkr.run",
        lambda tickers=None, fmt="csv": called.setdefault("tickers", tickers),
    )
    importlib.reload(main)
    seq = iter(["2", "u", "NVDA,AMD", "b", "0"])
    monkeypatch.setattr(builtins, "input", lambda _="": next(seq))
    main.parse_args = lambda: types.SimpleNamespace(quiet=True, format="csv")
    main.main()
    assert called["tickers"] == ["NVDA", "AMD"]
