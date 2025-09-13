import pandas as pd
import pytest
from portfolio_exporter.scripts import portfolio_greeks


def test_live_loader_is_overridable(monkeypatch):
    # provide fake data to avoid IBKR in CI
    fake = pd.DataFrame(
        [
            {
                "underlying": "FAKE",
                "secType": "OPT",
                "qty": 1,
                "multiplier": 100,
                "right": "C",
                "strike": 10,
                "expiry": "20240101",
                "delta": 0.5,
                "gamma": 0.1,
                "vega": 0.2,
                "theta": -0.03,
            },
            {
                "underlying": "FAK2",
                "secType": "STK",
                "qty": 50,
                "multiplier": 1,
                "right": "",
                "strike": 0.0,
                "expiry": "",
                "delta": 1.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": 0.0,
            },
        ],
        index=[1, 2],
    )
    monkeypatch.setattr(portfolio_greeks, "_load_positions", lambda: fake)
    res = portfolio_greeks.run(return_dict=True)
    assert res["legs"]["delta_exposure"] == pytest.approx(0.5 * 100 * 1 + 50 * 1 * 1.0)
