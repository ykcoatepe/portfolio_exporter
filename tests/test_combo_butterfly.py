import pandas as pd

from portfolio_exporter.core import combo
from portfolio_exporter.scripts import portfolio_greeks


def test_combo_butterfly(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "underlying": "XYZ",
                "qty": 1,
                "right": "C",
                "strike": 95.0,
                "expiry": "20240119",
                "delta": 0.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": 0.0,
            },
            {
                "underlying": "XYZ",
                "qty": -2,
                "right": "C",
                "strike": 100.0,
                "expiry": "20240119",
                "delta": 0.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": 0.0,
            },
            {
                "underlying": "XYZ",
                "qty": 1,
                "right": "C",
                "strike": 105.0,
                "expiry": "20240119",
                "delta": 0.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": 0.0,
            },
        ],
        index=[1, 2, 3],
    )
    monkeypatch.setattr(portfolio_greeks, "_load_positions", lambda: df)
    combos = combo.detect_combos(portfolio_greeks._load_positions(), mode="all")
    assert len(combos) == 1
    fly = combos.iloc[0]
    assert fly.structure == "Butterfly"
    assert fly.type == "butterfly"
    assert fly.width == 5.0
