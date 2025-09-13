import sqlite3
import pandas as pd

from portfolio_exporter.core import combo


def test_persists_and_closes(tmp_path, monkeypatch):
    db_path = tmp_path / "combos.db"
    monkeypatch.setattr(combo, "DB_PATH", db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        [
            {
                "underlying": "AAPL",
                "qty": 1,
                "right": "C",
                "strike": 100,
                "expiry": "20240119",
                "delta": 0.5,
                "gamma": 0.1,
                "vega": 0.2,
                "theta": -0.05,
            },
            {
                "underlying": "AAPL",
                "qty": -1,
                "right": "C",
                "strike": 105,
                "expiry": "20240119",
                "delta": -0.4,
                "gamma": -0.08,
                "vega": -0.15,
                "theta": 0.04,
            },
        ],
        index=[1, 2],
    )

    combos_df = combo.detect_combos(df)
    mapping = combo.fetch_persisted_mapping()
    assert mapping == {1: combos_df.index[0], 2: combos_df.index[0]}

    conn = sqlite3.connect(db_path)
    ts_closed = conn.execute(
        "SELECT ts_closed FROM combos WHERE combo_id=?", (combos_df.index[0],)
    ).fetchone()[0]
    conn.close()
    assert ts_closed is None

    # Now call with empty positions -> combo should be marked closed
    combo.detect_combos(df.iloc[0:0])

    conn = sqlite3.connect(db_path)
    ts_closed2 = conn.execute(
        "SELECT ts_closed FROM combos WHERE combo_id=?", (combos_df.index[0],)
    ).fetchone()[0]
    conn.close()
    assert ts_closed2 is not None
