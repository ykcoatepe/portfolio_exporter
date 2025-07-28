import builtins, types, importlib, main


def test_netliq_chart_show(monkeypatch):
    called = {}

    def fake_run(fmt="csv", plot=False):
        called["plot"] = plot

    monkeypatch.setattr(
        "portfolio_exporter.scripts.net_liq_history_export.run", fake_run
    )
    importlib.reload(main)
    seq = iter(["3", "v", "r", "0"])
    mock_input = lambda _="": next(seq)
    monkeypatch.setattr(builtins, "input", mock_input)
    monkeypatch.setattr(main, "input", mock_input)
    main.parse_args = lambda: types.SimpleNamespace(quiet=True, format="csv")
    main.main()
    assert called.get("plot") is True
