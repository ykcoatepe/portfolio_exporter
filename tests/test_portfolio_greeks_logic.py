import pandas as pd
import pytest
from portfolio_exporter.scripts import portfolio_greeks


def test_greeks_aggregation(monkeypatch):
    # Create fake positions with known greeks
    fake = pd.DataFrame(
        [
            {
                "symbol": "FAKE",
                "qty": 2,
                "delta": 0.5,
                "gamma": 0.1,
                "vega": 0.2,
                "theta": -0.05,
            },
            {
                "symbol": "FOO",
                "qty": 1,
                "delta": 1.0,
                "gamma": 0.2,
                "vega": 0.3,
                "theta": -0.02,
            },
        ]
    )
    # Monkeypatch the function that loads positions
    monkeypatch.setattr(
        "portfolio_exporter.scripts.portfolio_greeks._load_positions", lambda: fake
    )
    # Run with return_dict to inspect exposures
    result = portfolio_greeks.run(fmt="csv", return_dict=True)
    # Expected exposures = sum(qty*greek)
    assert result["delta_exposure"] == pytest.approx(2 * 0.5 + 1 * 1.0)
    assert result["gamma_exposure"] == pytest.approx(2 * 0.1 + 1 * 0.2)
    assert result["vega_exposure"] == pytest.approx(2 * 0.2 + 1 * 0.3)
    assert result["theta_exposure"] == pytest.approx(2 * -0.05 + 1 * -0.02)
