import pandas as pd
from portfolio_exporter.scripts.trades_report import _cluster_executions


def test_cluster_pnl_net_includes_commission():
    df = pd.DataFrame(
        {
            "symbol": ["SPY", "SPY"],
            "Side": ["BUY", "SELL"],
            "qty": [1, 1],
            "price": [1.0, 2.0],
            "multiplier": [100, 100],
            "datetime": pd.to_datetime(["2025-01-01", "2025-01-01"]),
            "perm_id": [111, 111],
            "commission": [1.5, 0.5],
        }
    )
    clusters, _ = _cluster_executions(df)
    assert "pnl_net" in clusters.columns
    # gross pnl = (1*1*100) + (-1*2*100) = -100
    # commission sum = 2.0 => net = -102.0
    val = float(clusters.loc[0, "pnl_net"]) if not clusters.empty else None
    assert abs(val - (-102.0)) < 1e-6

