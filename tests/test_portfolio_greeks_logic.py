import pandas as pd
import pytest

from portfolio_exporter.scripts import portfolio_greeks


def test_greeks_aggregation(monkeypatch):
    fake = pd.DataFrame(
        [
            {
                "underlying": "FAKE",
                "secType": "STK",
                "qty": 2,
                "multiplier": 1,
                "right": "",
                "strike": 0.0,
                "expiry": "",
                "delta": 0.5,
                "gamma": 0.1,
                "vega": 0.2,
                "theta": -0.05,
            },
            {
                "underlying": "FOO",
                "secType": "STK",
                "qty": 1,
                "multiplier": 1,
                "right": "",
                "strike": 0.0,
                "expiry": "",
                "delta": 1.0,
                "gamma": 0.2,
                "vega": 0.3,
                "theta": -0.02,
            },
        ],
        index=[1, 2],
    )

    monkeypatch.setattr(
        "portfolio_exporter.scripts.portfolio_greeks._load_positions", lambda: fake
    )

    result = portfolio_greeks.run(
        fmt="csv", write_positions=False, write_totals=False, return_dict=True
    )
    legs = result["legs"]

    assert legs["delta_exposure"] == pytest.approx(2 * 0.5 + 1 * 1.0)
    assert legs["gamma_exposure"] == pytest.approx(2 * 0.1 + 1 * 0.2)
    assert legs["vega_exposure"] == pytest.approx(2 * 0.2 + 1 * 0.3)
    assert legs["theta_exposure"] == pytest.approx(2 * -0.05 + 1 * -0.02)
