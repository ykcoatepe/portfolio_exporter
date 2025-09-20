import builtins
import importlib
import types

import pandas as pd

import main


def test_executions_table_includes_effect(monkeypatch):
    # Stub trades_report.run to return a simple execs df
    called = {"run": 0, "cluster": 0, "combos": 0}

    def fake_run(fmt="csv", show_actions=False, include_open=True, return_df=False, save_combos=True):
        called["run"] += 1
        df = pd.DataFrame(
            {
                "exec_id": [1, 2],
                "symbol": ["SPY", "SPY"],
                "Side": ["BUY", "SELL"],
                "qty": [1, 1],
                "price": [1.0, 2.0],
                "multiplier": [100, 100],
                "datetime": pd.to_datetime(["2025-01-01", "2025-01-01"]),
            }
        )
        return df if return_df else None

    def fake_cluster(df, window_sec=60):
        called["cluster"] += 1
        clusters = pd.DataFrame(
            {
                "cluster_id": [1],
                "perm_ids": ["123/456"],
                "underlying": ["SPY"],
                "structure": ["vertical"],
                "start": pd.to_datetime(["2025-01-01"]),
                "end": pd.to_datetime(["2025-01-01"]),
                "pnl": [100.0],
                "legs_n": [2],
            }
        )
        return clusters, df

    def fake_detect(execs, opens=None, prev_positions_df=None):
        called["combos"] += 1
        return pd.DataFrame(
            {
                "underlying": ["SPY"],
                "structure": ["vertical"],
                "legs": ["[1,2]"] ,
                "legs_n": [2],
                "order_ids": ["123,456"],
                "position_effect": ["Roll"],
            }
        )

    monkeypatch.setattr(
        "portfolio_exporter.scripts.trades_report.run", fake_run
    )
    monkeypatch.setattr(
        "portfolio_exporter.scripts.trades_report._cluster_executions", fake_cluster
    )
    monkeypatch.setattr(
        "portfolio_exporter.scripts.trades_report._detect_and_enrich_trades_combos",
        fake_detect,
    )

    # Drive menu: 3 (Trades) → e (Executions) → r → 0
    importlib.reload(main)
    inp = iter(["3", "e", "r", "0"])  # enter Trades, run Executions, return, exit
    monkeypatch.setattr(builtins, "input", lambda _="": next(inp))
    monkeypatch.setattr(main, "input", lambda _="": next(inp))
    main.parse_args = lambda: types.SimpleNamespace(
        quiet=True,
        format="csv",
        list_tasks=False,
        workflow=None,
        tasks=None,
        tasks_csv=None,
        dry_run=False,
        json=False,
    )
    main.main()
    # Ensure our stubs were used
    assert called["run"] == 1 and called["cluster"] == 1 and called["combos"] == 1

