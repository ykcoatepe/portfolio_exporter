import math

import pandas as pd

from portfolio_exporter.core.ib import quote_option


def test_fallback(monkeypatch):
    """Ensure Black-Scholes greeks are used when IBKR ones are missing."""

    class DummyIB:
        def isConnected(self) -> bool:  # pragma: no cover - simple stub
            return False

    monkeypatch.setattr("portfolio_exporter.core.ib._ib", lambda: DummyIB())

    fake_chain = type(
        "OC",
        (),
        {
            "calls": pd.DataFrame(
                [
                    {
                        "strike": 200,
                        "bid": 2.4,
                        "ask": 2.6,
                        "impliedVolatility": 0.22,
                    }
                ]
            ),
            "puts": pd.DataFrame(
                [
                    {
                        "strike": 200,
                        "bid": 2.4,
                        "ask": 2.6,
                        "impliedVolatility": 0.22,
                    }
                ]
            ),
        },
    )
    monkeypatch.setattr("yfinance.Ticker.option_chain", lambda self, exp: fake_chain)

    fake_hist = pd.DataFrame({"Close": [150.0]})
    monkeypatch.setattr("yfinance.Ticker.history", lambda self, period: fake_hist)

    q = quote_option("AAPL", "2099-01-21", 200, "C")
    assert all(not math.isnan(q[g]) for g in ["delta", "gamma", "vega", "theta"])
