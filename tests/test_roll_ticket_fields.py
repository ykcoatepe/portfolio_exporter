import builtins
import json
import datetime as dt
from pathlib import Path

import pandas as pd

from portfolio_exporter.scripts import roll_manager
from portfolio_exporter.core.config import settings
from portfolio_exporter.scripts import portfolio_greeks


def _prepare(monkeypatch, tmp_path: Path):
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    exp = tomorrow.isoformat()

    pos_df = pd.DataFrame(
        {
            "underlying": ["XYZ", "XYZ"],
            "qty": [-1, 1],
            "right": ["C", "C"],
            "strike": [100.0, 105.0],
            "expiry": [exp, exp],
            "delta": [-0.5, 0.5],
            "theta": [0.1, -0.1],
            "multiplier": [100, 100],
        },
        index=[1, 2],
    )
    monkeypatch.setattr(portfolio_greeks, "_load_positions", lambda: pos_df)

    combo_df = pd.DataFrame(
        {
            "structure": ["VertCall"],
            "underlying": ["XYZ"],
            "expiry": [exp],
            "qty": [-1],
            "delta": [0.0],
            "theta": [0.0],
            "legs": [[1, 2]],
        },
        index=["c1"],
    )
    monkeypatch.setattr(roll_manager, "detect_combos", lambda df: combo_df)

    chain_df = pd.DataFrame(
        [
            {"strike": 100.0, "right": "C", "mid": 1.0, "delta": 0.2, "theta": -0.02},
            {"strike": 105.0, "right": "C", "mid": 0.5, "delta": 0.15, "theta": -0.01},
        ]
    )
    monkeypatch.setattr(
        roll_manager, "fetch_chain", lambda sym, exp, strikes=None: chain_df
    )

    monkeypatch.setattr(settings, "output_dir", str(tmp_path))


def _run(monkeypatch, tmp_path: Path) -> Path:
    _prepare(monkeypatch, tmp_path)
    inputs = iter([" ", "r", "q"])
    monkeypatch.setattr(builtins, "input", lambda *a, **k: next(inputs))
    roll_manager.run()
    ticket = list(Path(tmp_path).glob("roll_ticket_*.json"))[0]
    return ticket


def test_roll_ticket_fields(monkeypatch, tmp_path):
    ticket_path = _run(monkeypatch, tmp_path)
    data = json.loads(ticket_path.read_text())
    combo = data["combos"][0]
    assert len(combo["legs_close"]) == 2
    assert len(combo["legs_open"]) == 2
