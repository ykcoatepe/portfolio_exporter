import math
import types

import pandas as pd
from portfolio_exporter.core import ib as core_ib


def test_quote_option_fallback(monkeypatch):
    monkeypatch.setattr(core_ib, "_ib_singleton", None)
    monkeypatch.setattr(core_ib, "_IB_PORT", 9999)

    def fake_chain(self, date):
        return types.SimpleNamespace(
            calls=pd.DataFrame(
                {
                    "strike": [100],
                    "bid": [1.0],
                    "ask": [1.2],
                    "impliedVolatility": [0.25],
                }
            ),
            puts=pd.DataFrame(
                {
                    "strike": [100],
                    "bid": [2.0],
                    "ask": [2.2],
                    "impliedVolatility": [0.30],
                }
            ),
        )

    monkeypatch.setattr("yfinance.Ticker.option_chain", fake_chain)
    q = core_ib.quote_option("FAKE", "2099-01-01", 100, "C")
    assert math.isclose(q["mid"], 1.1, rel_tol=1e-8)
