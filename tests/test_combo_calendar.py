import pandas as pd

from portfolio_exporter.core import combo
from portfolio_exporter.scripts import portfolio_greeks


def test_combo_calendar(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "underlying": "XYZ",
                "qty": 1,
                "right": "C",
                "strike": 100.0,
                "expiry": "20240119",
                "delta": 0.5,
                "gamma": 0.1,
                "vega": 0.2,
                "theta": -0.05,
            },
            {
                "underlying": "XYZ",
                "qty": -1,
                "right": "C",
                "strike": 100.0,
                "expiry": "20240216",
                "delta": -0.4,
                "gamma": -0.08,
                "vega": -0.15,
                "theta": 0.04,
            },
        ],
        index=[1, 2],
    )

    async def fake_loader():
        return df

    monkeypatch.setattr(portfolio_greeks, "_load_positions", fake_loader)
    monkeypatch.setattr(portfolio_greeks, "load_positions_sync", lambda: df)
    combos = combo.detect_combos(portfolio_greeks.load_positions_sync(), mode="all")
    assert len(combos) == 1
    cal = combos.iloc[0]
    assert cal.structure == "Calendar"
    assert cal.type == "calendar"
    assert cal.width == 0.0
