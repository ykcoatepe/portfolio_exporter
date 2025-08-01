import pandas as pd
from pathlib import Path
from portfolio_exporter.scripts import portfolio_greeks


def test_greeks_dual_files(tmp_path, monkeypatch):
    fake = pd.DataFrame(
        [
            {
                "symbol": "FAKE",
                "qty": 2,
                "mult": 100,
                "delta": 0.5,
                "gamma": 0.1,
                "vega": 0.2,
                "theta": -0.05,
            },
            {
                "symbol": "FOO",
                "qty": 1,
                "mult": 1,
                "delta": 1.0,
                "gamma": 0.2,
                "vega": 0.3,
                "theta": -0.02,
            },
        ]
    )
    monkeypatch.setattr(portfolio_greeks, "_load_positions", lambda: fake)
    # redirect output dir
    monkeypatch.setattr(
        "portfolio_exporter.core.config.settings",
        type("X", (object,), {"output_dir": str(tmp_path)}),
    )
    portfolio_greeks.run(fmt="csv")
    assert (tmp_path / "portfolio_greeks_totals.csv").exists()
    assert (tmp_path / "portfolio_greeks_positions.csv").exists()
