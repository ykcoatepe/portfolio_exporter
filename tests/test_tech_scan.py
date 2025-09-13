import pandas as pd
import builtins
from portfolio_exporter.scripts import tech_scan


def test_tech_scan_saves(monkeypatch, tmp_path):
    # Patch yfinance.download to return dummy OHLC
    dummy = pd.DataFrame(
        {
            "Open": [1, 2, 3],
            "High": [1, 2, 3],
            "Low": [1, 2, 3],
            "Close": [1, 2, 3],
            "Adj Close": [1, 2, 3],
            "Volume": [100, 120, 130],
        },
        index=pd.date_range("2024-01-01", periods=3),
    )
    monkeypatch.setattr("yfinance.download", lambda *a, **k: dummy)
    # Patch io.save to capture format
    saved = {}
    monkeypatch.setattr(
        "portfolio_exporter.core.io.save",
        lambda df, name, fmt="csv", outdir=None: saved.setdefault("ok", fmt),
    )
    tech_scan.run(tickers=["ZZZZ"], fmt="pdf")
    assert saved.get("ok") == "pdf"
