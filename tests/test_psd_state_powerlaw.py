from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import psd.web.app as web_app
from psd.core import store
from psd.web.config import Settings

pytestmark = pytest.mark.integration


def test_state_overlays_powerlaw_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("PSD_DB", str(db_path))
    store.init()
    store.write_snapshot(
        {
            "ts": 1_700_000_000.0,
            "positions": [],
            "positions_view": {
                "single_stocks": [],
                "option_combos": [],
                "single_options": [],
            },
            "quotes": {},
            "risk": {},
            "powerlaw": {"as_of": "2025-01-01"},
        }
    )
    monkeypatch.setattr(
        web_app,
        "load_powerlaw_snapshot",
        lambda: {"as_of": "2025-01-10", "stale": False},
    )

    app = web_app.create_app(Settings(test_mode=True, disable_background=True))
    with TestClient(app) as client:
        response = client.get("/state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["powerlaw"]["as_of"] == "2025-01-10"
