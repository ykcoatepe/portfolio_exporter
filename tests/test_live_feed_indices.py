import pandas as pd, pytest
from portfolio_exporter.scripts import live_feed


def test_always_indices(monkeypatch, tmp_path):
    # fake loader returns just ["AAPL"]
    monkeypatch.setattr(live_feed, "_load_portfolio_tickers", lambda: ["AAPL"])

    # stub snapshot function to avoid network
    called = {}

    def fake_snapshot(ticker_list, *_a, **_kw):
        called["tickers"] = ticker_list
        # return minimal df
        return pd.DataFrame({"symbol": ticker_list, "price": 100})

    monkeypatch.setattr(live_feed, "_snapshot_quotes", fake_snapshot)

    live_feed.run(fmt="csv", include_indices=True, return_df=False)
    expected = {"AAPL", "SPY", "QQQ", "IWM", "DIA", "VIX"}
    assert set(called["tickers"]) == expected
