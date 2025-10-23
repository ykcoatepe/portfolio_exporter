import pandas as pd

from portfolio_exporter.core import combo
from portfolio_exporter.scripts import portfolio_greeks


def test_combo_condor(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "underlying": "XYZ",
                "qty": 1,
                "right": "P",
                "strike": 95.0,
                "expiry": "20240119",
                "delta": 0.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": 0.0,
            },
            {
                "underlying": "XYZ",
                "qty": -1,
                "right": "P",
                "strike": 100.0,
                "expiry": "20240119",
                "delta": 0.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": 0.0,
            },
            {
                "underlying": "XYZ",
                "qty": -1,
                "right": "C",
                "strike": 110.0,
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
                "strike": 115.0,
                "expiry": "20240119",
                "delta": 0.0,
                "gamma": 0.0,
                "vega": 0.0,
                "theta": 0.0,
            },
        ],
        index=[1, 2, 3, 4],
    )

    async def fake_loader():
        return df

    monkeypatch.setattr(portfolio_greeks, "_load_positions", fake_loader)
    monkeypatch.setattr(portfolio_greeks, "load_positions_sync", lambda: df)
    combos = combo.detect_combos(portfolio_greeks.load_positions_sync(), mode="all")
    assert len(combos) == 1
    condor = combos.iloc[0]
    assert condor.structure == "Condor"
    assert condor.type == "condor"
    assert condor.width == 5.0
