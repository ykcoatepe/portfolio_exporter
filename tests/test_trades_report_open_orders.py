import pandas as pd
import pytest
from portfolio_exporter.scripts import trades_report


def test_include_open(monkeypatch):
    execs = pd.DataFrame(
        [
            {
                "Side": "BOT",
                "secType": "OPT",
                "Liquidation": 0,
                "lastLiquidity": 1,
                "OrderRef": "",
                "symbol": "FAKE",
            }
        ]
    )
    opens = pd.DataFrame(
        [
            {
                "symbol": "FAKE",
                "secType": "OPT",
                "Side": "BUY",
                "Qty": 1,
                "OrderRef": "",
                "Action": "Open",
            }
        ]
    )
    monkeypatch.setattr(trades_report, "_load_trades", lambda: execs)
    monkeypatch.setattr(trades_report, "_load_open_orders", lambda: opens)
    out = trades_report.run(
        fmt="csv", show_actions=True, include_open=True, return_df=True
    )
    assert len(out) == 2
    assert "Open" in out["Action"].values
