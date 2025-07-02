import pandas as pd
from src import analysis


def test_calc_portfolio_greeks_equities_only():
    df = pd.DataFrame({"underlying": ["AAPL"], "position": [10], "multiplier": [1]})
    res = analysis.calc_portfolio_greeks(df)
    assert "PORTFOLIO" in res.index
    assert res.loc["PORTFOLIO", "delta"] == 0


def test_calc_portfolio_greeks_empty():
    res = analysis.calc_portfolio_greeks(pd.DataFrame())
    assert res.empty
