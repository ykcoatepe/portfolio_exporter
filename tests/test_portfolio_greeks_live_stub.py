import pandas as pd
import pytest
from portfolio_exporter.scripts import portfolio_greeks


def test_live_loader_is_overridable(monkeypatch):
    # provide fake data to avoid IBKR in CI
    fake = pd.DataFrame(
        [
            {
                "symbol": "FAKE",
                "secType": "OPT",
                "qty": 1,
                "multiplier": 100,
                "delta": 0.5,
                "gamma": 0.1,
                "vega": 0.2,
                "theta": -0.03,
            },
            {
                "symbol": "FAK2",
                "secType": "STK",
                "qty": 50,
                "multiplier": 1,
                "delta": 1.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": 0.0,
            },
        ]
    )
    monkeypatch.setattr(portfolio_greeks, "_load_positions", lambda: fake)
    res = portfolio_greeks.run(return_dict=True)
    assert res["delta_exposure"] == pytest.approx(0.5 * 100 * 1 + 50 * 1 * 1.0)
