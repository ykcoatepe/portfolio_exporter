import pandas as pd
import pytest
from portfolio_exporter.scripts import trades_report


def test_action_tags(monkeypatch):
    dummy = pd.DataFrame(
        [
            {
                "secType": "OPT",
                "Side": "BOT",
                "Liquidation": 0,
                "lastLiquidity": 1,
                "OrderRef": "",
            },
            {
                "secType": "OPT",
                "Side": "SLD",
                "Liquidation": 0,
                "lastLiquidity": 1,
                "OrderRef": "",
            },
            {
                "secType": "OPT",
                "Side": "SLD",
                "Liquidation": 2,
                "lastLiquidity": 2,
                "OrderRef": "",
            },
            {
                "secType": "BAG",
                "Side": "BOT",
                "Liquidation": 0,
                "lastLiquidity": 1,
                "OrderRef": "",
            },
            {
                "secType": "OPT",
                "Side": "BOT",
                "Liquidation": 0,
                "lastLiquidity": 1,
                "OrderRef": "ROLL_123",
            },
        ]
    )
    monkeypatch.setattr(
        "portfolio_exporter.scripts.trades_report._load_executions", lambda: dummy
    )
    df = trades_report.run(fmt="csv", show_actions=True, return_df=True)
    assert list(df["Action"]) == ["Buy", "Sell", "Close", "Combo", "Roll"]
