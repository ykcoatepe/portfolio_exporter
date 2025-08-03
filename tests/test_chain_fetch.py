import pandas as pd
from portfolio_exporter.core import chain


def test_fetch_chain_stub(monkeypatch):
    def fake_quote(symbol, expiry, strike, right):
        return {
            "mid": 1.23,
            "bid": 1.2,
            "ask": 1.26,
            "delta": 0.5,
            "gamma": 0.1,
            "vega": 0.2,
            "theta": -0.03,
            "iv": 0.25,
        }

    monkeypatch.setattr(chain, "quote_option", fake_quote)
    out = chain.fetch_chain("FAKE", "2099-01-01", strikes=[10, 12])
    assert len(out) == 4
    assert {"strike", "right", "mid", "delta", "iv"}.issubset(out.columns)
