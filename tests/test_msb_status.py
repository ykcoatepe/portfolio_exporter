from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from psd.core import store
from psd.web.app import create_app
from psd.web.config import Settings


def _store_sample_row(date_str: str) -> None:
    df = pd.DataFrame(
        {
            "date": [date_str],
            "hy": [2.5],
            "vx1": [15.0],
            "vx2": [16.0],
            "z_hy": [0.0],
            "term_ratio": [-0.0625],
            "cal_spread_pct": [-0.0625],
            "cal_spread_abs": [-1.0],
            "saturated": [0],
            "hy_score": [20],
            "vix_score": [10],
            "msb": [30],
            "color": ["yellow"],
            "triggers": ["[]"],
            "winsor_clipped_n": [0],
            "cooldown_until": [None],
        }
    )
    df["date"] = pd.to_datetime(df["date"])
    store.store_msb(df.set_index("date"))


def test_msb_status_unknown_includes_source(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PSD_DB", str(tmp_path / "psd.db"))
    app = create_app(Settings(test_mode=True, disable_background=True))
    client = TestClient(app)

    resp = client.get("/msb/status")
    body = resp.json()

    assert resp.status_code == 200
    assert body["status"] == "unknown"
    assert body["source"] == "vendor"
    # data_age_seconds may be null when no record exists
    assert "data_age_seconds" in body


def test_msb_status_reports_age_and_source(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PSD_DB", str(tmp_path / "psd.db"))
    store.init()
    today = datetime.now(timezone.utc).date().isoformat()
    _store_sample_row(today)

    app = create_app(Settings(test_mode=True, disable_background=True))
    app.state.msb_refresh = {
        "status": "updated",
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "last_date": today,
        "detail": None,
        "source": "ibkr",
        "data_age_seconds": 0.0,
    }
    client = TestClient(app)

    resp = client.get("/msb/status")
    body = resp.json()

    assert resp.status_code == 200
    assert body["status"] == "updated"
    assert body["last_date"] == today
    assert body["source"] == "ibkr"
    assert body["data_age_seconds"] is not None
    assert body["data_age_seconds"] >= 0.0
