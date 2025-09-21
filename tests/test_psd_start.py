from __future__ import annotations

import json
from typing import Any


def test_psd_start_opens_browser_and_broadcasts(monkeypatch: Any) -> None:
    opened: list[str] = []

    def fake_open(url: str) -> None:
        opened.append(url)

    monkeypatch.setattr("webbrowser.open", fake_open, raising=False)

    # Force server.start to return a fixed host/port immediately
    import src.psd.web.server as web_server

    def fake_start(host: str = "127.0.0.1", port: int = 0, *, background: bool = True) -> tuple[str, int]:
        return host, 8123

    monkeypatch.setattr(web_server, "start", fake_start)

    # Probe: first 2 tries empty, then non-empty
    import src.psd.datasources.ibkr as ibkr

    calls = {"n": 0}

    def fake_get_positions(cfg: dict[str, Any] | None = None):
        calls["n"] += 1
        if calls["n"] < 3:
            return []
        return [{"symbol": "SPY", "mark": 1.0}]

    monkeypatch.setattr(ibkr, "get_positions", fake_get_positions)

    # Capture broadcasts via sched.run_loop hook
    captured: list[dict[str, Any]] = []

    def fake_broadcast(dto: dict[str, Any]) -> None:
        json.dumps(dto)
        captured.append(dto)

    monkeypatch.setattr(web_server, "broadcast", fake_broadcast)

    from psd.runner import start_psd

    # Run bounded starter
    host, port = start_psd(loops=2, interval_override=0.01)
    assert host == "127.0.0.1" and isinstance(port, int)
    assert any(u.startswith("http://127.0.0.1:8123") for u in opened)
    assert len(captured) == 2
