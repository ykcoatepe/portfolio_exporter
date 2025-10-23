import pandas as pd, pytest, pathlib
from portfolio_exporter.scripts import portfolio_greeks


def test_greeks_files(monkeypatch, tmp_path):
    fake = pd.DataFrame(
        [
            {
                "underlying": "OPT1",
                "secType": "OPT",
                "qty": 1,
                "multiplier": 100,
                "right": "C",
                "strike": 10,
                "expiry": "20240101",
                "delta": 0.5,
                "gamma": 0.1,
                "vega": 0.3,
                "theta": -0.04,
            },
            {
                "underlying": "STK1",
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

    async def fake_loader():
        return fake

    monkeypatch.setattr(portfolio_greeks, "_load_positions", fake_loader)
    monkeypatch.setattr(portfolio_greeks, "load_positions_sync", lambda: fake)
    monkeypatch.setattr(
        "portfolio_exporter.core.config.settings",
        type("X", (object,), {"output_dir": str(tmp_path)}),
    )
    portfolio_greeks.run(fmt="csv")
    assert (tmp_path / "portfolio_greeks_positions.csv").exists()
    assert (tmp_path / "portfolio_greeks_totals.csv").exists()
    totals = pd.read_csv(tmp_path / "portfolio_greeks_totals.csv")
    exp_delta = 1 * 100 * 0.5 + 50 * 1 * 1.0
    assert totals["delta_exposure"].iloc[0] == pytest.approx(exp_delta)
