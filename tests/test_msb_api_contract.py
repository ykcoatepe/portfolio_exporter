from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import psd.web.app as web_app
from psd.core import store
from psd.web.config import Settings


@pytest.fixture()
def seeded_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "psd.db"
    monkeypatch.setenv("PSD_DB", str(db_path))
    store.init()
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    frame = pd.DataFrame(
        {
            "hy": [1.0, 1.1, 1.2],
            "vx1": [15.0, 15.5, 16.0],
            "vx2": [16.5, 16.0, 15.5],
            "z_hy": [0.1, 0.2, 0.3],
            "term_ratio": [0.9, 1.0, 1.1],
            "cal_spread_pct": [0.02, 0.025, 0.03],
            "cal_spread_abs": [0.5, 0.6, 0.7],
            "saturated": [False, False, True],
            "hy_score": [1, 2, 3],
            "vix_score": [4, 5, 6],
            "msb": [10, 20, 30],
            "color": ["green", "yellow", "red"],
            "triggers": [["alpha"], [], ["beta", "gamma"]],
            "winsor_clipped_n": [0, 1, 2],
            "cooldown_until": [pd.NaT, pd.Timestamp("2024-01-05"), pd.NaT],
        },
        index=dates,
    )
    frame.index.name = "date"
    store.store_msb(frame)


def test_msb_current_returns_latest(seeded_db: None) -> None:
    app = web_app.create_app(Settings(test_mode=True, disable_background=True))
    with TestClient(app) as client:
        response = client.get("/msb/current")

    assert response.status_code == 200
    payload = response.json()
    assert payload["date"] == "2024-01-03"
    assert payload["msb"] == 30
    assert payload["color"] == "red"
    assert payload["triggers"] == ["beta", "gamma"]


def test_msb_history_limits_days(seeded_db: None) -> None:
    app = web_app.create_app(Settings(test_mode=True, disable_background=True))
    with TestClient(app) as client:
        response = client.get("/msb/history", params={"days": 2})

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 2
    dates = [entry["date"] for entry in payload]
    assert dates == ["2024-01-03", "2024-01-02"]
    assert all("triggers" in entry for entry in payload)


def test_msb_history_parquet_round_trip(seeded_db: None) -> None:
    app = web_app.create_app(Settings(test_mode=True, disable_background=True))
    with TestClient(app) as client:
        response = client.get("/msb/history.parquet", params={"days": 3})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].endswith("msb_history.parquet")

    buffer = io.BytesIO(response.content)
    frame = pd.read_parquet(buffer)
    assert list(frame.columns) == [
        "date",
        "hy",
        "vx1",
        "vx2",
        "z_hy",
        "term_ratio",
        "cal_spread_pct",
        "cal_spread_abs",
        "saturated",
        "hy_score",
        "vix_score",
        "msb",
        "color",
        "triggers",
        "winsor_clipped_n",
        "cooldown_until",
    ]
    assert len(frame) == 3
    assert frame.iloc[0]["date"] == "2024-01-03"
