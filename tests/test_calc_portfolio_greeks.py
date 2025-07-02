import pandas as pd
from src import analysis


def test_calc_portfolio_greeks_equities_only():
    df = pd.DataFrame({"underlying": ["AAPL"], "position": [10], "multiplier": [1]})
    res = analysis.calc_portfolio_greeks(df)
    assert "PORTFOLIO_TOTAL" in res.index
    assert res.loc["PORTFOLIO_TOTAL", "delta"] == 0


def test_calc_portfolio_greeks_empty():
    res = analysis.calc_portfolio_greeks(pd.DataFrame())
    assert res.empty

def test_calc_portfolio_greeks_filter_indices():
    # Sample exposures including an index underlying that should be filtered
    df = pd.DataFrame({
        "underlying": ["AAPL", "TSLA", "VIX"],
        "position": [10, 5, 1],
        "multiplier": [1, 1, 1],
        "delta": [2.0, 3.0, 4.0],
        "gamma": [0.1, 0.2, 0.3],
        "vega": [0.4, 0.5, 0.6],
        "theta": [0.0, 0.0, 0.0],
        "rho": [0.0, 0.0, 0.0],
    })
    res = analysis.calc_portfolio_greeks(df)
    # VIX row should be dropped by default
    assert "VIX" not in res.index
    # Only AAPL, TSLA and total remain
    assert set(res.index) == {"AAPL", "TSLA", "PORTFOLIO_TOTAL"}
    # Total delta equals sum of AAPL and TSLA deltas
    expected = res.loc["AAPL", "delta"] + res.loc["TSLA", "delta"]
    assert res.loc["PORTFOLIO_TOTAL", "delta"] == expected
