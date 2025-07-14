import pandas as pd, types, pytest
from portfolio_exporter.core import quotes


def test_yf_fallback(monkeypatch):
    # force ib to error
    monkeypatch.setattr(
        quotes, "_ibkr_quotes", lambda t: (_ for _ in ()).throw(ConnectionError)
    )
    # mock yfinance
    dummy = pd.DataFrame({"Close": [1.23]}, index=[0])
    monkeypatch.setattr(quotes, "_yf_quotes", lambda t: {"AAPL": 1.23})
    out = quotes.snapshot(["AAPL"])
    assert out["AAPL"] == 1.23
