import types


def test_pre_market_dispatch(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "portfolio_exporter.scripts.update_tickers.run",
        lambda fmt="csv": calls.append("tickers"),
    )
    import main, importlib

    importlib.reload(main)
    monkeypatch.setattr(main, "input", lambda _: "s\nr\n0")
    main.parse_args = lambda: types.SimpleNamespace(quiet=True, format="csv")
    main.main()
    assert "tickers" in calls
