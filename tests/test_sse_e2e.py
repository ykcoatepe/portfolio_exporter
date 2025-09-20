from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any, Callable

import pytest
from starlette.testclient import TestClient

import sys

SRC_ROOT = Path(__file__).resolve().parents[1]
SRC_SRC = SRC_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SRC_SRC) not in sys.path:
    sys.path.insert(0, str(SRC_SRC))

from psd.core import store
import psd.web.app as web_app


def _read_events(
    resp: Any,
    limit: int | None = None,
    on_event: Callable[[tuple[int | None, str, dict[str, Any]]], None] | None = None,
) -> list[tuple[int | None, str, dict[str, Any]]]:
    events: list[tuple[int | None, str, dict[str, Any]]] = []
    current = {"id": None, "event": None, "data": []}
    for raw_line in resp.iter_lines():
        line = raw_line.decode("utf-8") if isinstance(raw_line, (bytes, bytearray)) else raw_line
        if line == "":
            if current["event"]:
                payload_str = "\n".join(current["data"]).strip()
                payload = json.loads(payload_str or "{}")
                event_id = int(current["id"]) if current["id"] is not None else None
                event = (event_id, current["event"], payload)
                events.append(event)
                if on_event is not None:
                    on_event(event)
            current = {"id": None, "event": None, "data": []}
            if limit is not None and len(events) >= limit:
                break
            continue
        if line.startswith("id:"):
            current["id"] = line[3:].strip() or None
        elif line.startswith("event:"):
            current["event"] = line[6:].strip()
        elif line.startswith("data:"):
            current["data"].append(line[5:])
    return events
def test_sse_bootstrap_and_monotonic_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ = tmp_path  # ensure fixture consumed for API compatibility
    monkeypatch.setenv("PSD_SSE_TEST_MODE", "1")
    monkeypatch.setattr(web_app, "TEST_MODE", True)
    monkeypatch.setattr(web_app, "init", lambda _app=None: None)
    monkeypatch.setattr(store, "init", lambda: None)

    snapshot = {
        "ts": "2024-01-01T00:00:00Z",
        "positions": [],
        "quotes": {},
        "risk": {},
    }
    events_queue = deque(
        (
            idx,
            "health",
            {"ibkr_connected": bool(idx % 2), "data_age_s": float(idx)},
        )
        for idx in range(11, 16)
    )
    head = 10

    monkeypatch.setattr(web_app, "latest_snapshot", lambda: snapshot)
    monkeypatch.setattr(web_app, "max_event_id", lambda: head)

    def fake_tail_events(last_id: int = 0, limit: int = 200):
        batch: list[tuple[int, str, dict[str, Any]]] = []
        while events_queue and events_queue[0][0] <= last_id:
            events_queue.popleft()
        while events_queue and len(batch) < limit:
            batch.append(events_queue.popleft())
        return batch

    monkeypatch.setattr(web_app, "tail_events", fake_tail_events)

    with TestClient(web_app.app) as client:
        url = (
            "/stream?test_limit_ids=5&test_limit_frames=50&"
            "test_idle_ms=1000&test_max_ms=2000"
        )
        headers = {"Accept": "text/event-stream"}
        with client.stream("GET", url, headers=headers, timeout=5.0) as resp:
            events = _read_events(resp)

    assert events, "expected at least one SSE event"
    assert events[0][0] is None and events[0][1] == "snapshot"
    ids = [eid for eid, _, _ in events[1:] if eid is not None]
    assert ids and ids[0] > head
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_sse_resume(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ = tmp_path  # ensure fixture consumed for API compatibility
    monkeypatch.setenv("PSD_SSE_TEST_MODE", "1")
    monkeypatch.setattr(web_app, "TEST_MODE", True)
    monkeypatch.setattr(web_app, "init", lambda _app=None: None)
    monkeypatch.setattr(store, "init", lambda: None)

    snapshot = {
        "ts": "2024-01-02T00:00:00Z",
        "positions": [],
        "quotes": {},
        "risk": {},
    }
    last = 42
    events_queue = deque(
        (
            last + idx,
            "health",
            {"ibkr_connected": bool(idx % 2), "data_age_s": float(idx)},
        )
        for idx in range(1, 4)
    )

    monkeypatch.setattr(web_app, "latest_snapshot", lambda: snapshot)
    monkeypatch.setattr(web_app, "max_event_id", lambda: last)

    def fake_tail_events(last_id: int = 0, limit: int = 200):
        batch: list[tuple[int, str, dict[str, Any]]] = []
        while events_queue and events_queue[0][0] <= last_id:
            events_queue.popleft()
        while events_queue and len(batch) < limit:
            batch.append(events_queue.popleft())
        return batch

    monkeypatch.setattr(web_app, "tail_events", fake_tail_events)

    headers = {
        "Accept": "text/event-stream",
        "Last-Event-ID": str(last),
    }
    url = "/stream?test_limit_ids=3&test_idle_ms=500&test_max_ms=2000"
    with TestClient(web_app.app) as client:
        with client.stream("GET", url, headers=headers, timeout=5.0) as resp:
            events = _read_events(resp)

    ids = [eid for eid, _, _ in events if eid is not None]
    assert ids and all(event_id > last for event_id in ids)
