import types, importlib, builtins, main


def test_live_menu_dispatch(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "portfolio_exporter.scripts.live_feed.run",
        lambda: calls.append("q"),
    )
    # reload main so patch is in effect
    importlib.reload(main)
    # simulate: choose menu 2, press q, then b, then exit
    seq = iter(["2", "q", "b", "0"])
    mock_input = lambda _="": next(seq)
    monkeypatch.setattr(builtins, "input", mock_input)
    monkeypatch.setattr(main, "input", mock_input)
    main.parse_args = lambda: types.SimpleNamespace(quiet=True, format="csv")
    main.main()
    assert "q" in calls
