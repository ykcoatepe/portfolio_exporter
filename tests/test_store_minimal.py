from __future__ import annotations

from psd.core import store


def test_store_roundtrip(monkeypatch, tmp_path):
    db_path = tmp_path / "store.db"
    monkeypatch.setenv("PSD_DB", str(db_path))

    store.init()

    snapshot = {"positions": [{"symbol": "AAPL", "qty": 10}]}
    snapshot_id = store.write_snapshot(snapshot)
    assert snapshot_id >= 1

    assert store.latest_snapshot() == snapshot

    store.write_health(ibkr_connected=True, data_age_s=3.5)

    events = store.tail_events()
    assert [kind for _, kind, _ in events] == ["snapshot", "health"]
    assert events[0][2] == snapshot
    assert events[1][2] == {"ibkr_connected": True, "data_age_s": 3.5}

    # Verify tailing from the first event only returns the health update.
    health_events = store.tail_events(last_id=events[0][0])
    assert len(health_events) == 1
    assert health_events[0][1] == "health"
