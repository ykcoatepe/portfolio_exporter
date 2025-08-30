import sqlite3
import pandas as pd

from portfolio_exporter.core import combo
from portfolio_exporter.scripts import portfolio_greeks


def test_roll_lineage(tmp_path, monkeypatch):
    db_path = tmp_path / "combos.db"
    monkeypatch.setattr(combo, "DB_PATH", db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    df1 = pd.DataFrame(
        [
            {
                "underlying": "XYZ",
                "qty": -1,
                "right": "C",
                "strike": 100.0,
                "expiry": "20240119",
                "delta": -0.5,
                "gamma": -0.1,
                "vega": -0.2,
                "theta": 0.05,
            },
            {
                "underlying": "XYZ",
                "qty": 1,
                "right": "C",
                "strike": 105.0,
                "expiry": "20240119",
                "delta": 0.4,
                "gamma": 0.08,
                "vega": 0.15,
                "theta": -0.04,
            },
        ],
        index=[1, 2],
    )
    monkeypatch.setattr(portfolio_greeks, "_load_positions", lambda: df1)
    combos1 = combo.detect_combos(portfolio_greeks._load_positions(), mode="all")
    parent_id = combos1.index[0]

    df2 = df1.copy()
    df2["expiry"] = "20240216"
    df2.index = [3, 4]
    monkeypatch.setattr(portfolio_greeks, "_load_positions", lambda: df2)
    combos2 = combo.detect_combos(portfolio_greeks._load_positions(), mode="all")
    child_id = combos2.index[0]

    assert combos2.loc[child_id, "parent_combo_id"] == parent_id

    conn = sqlite3.connect(db_path)
    closed = conn.execute(
        "SELECT closed_date FROM combos WHERE combo_id=?", (parent_id,)
    ).fetchone()[0]
    conn.close()
    assert closed is not None
