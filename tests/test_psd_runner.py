from __future__ import annotations

from typing import Any


def test_runner_starts_and_broadcasts(monkeypatch: Any) -> None:
    opened = {"n": 0}

    # Do not actually open a browser in tests
    def fake_open(url: str) -> None:
        opened["n"] += 1

    monkeypatch.setattr("webbrowser.open", fake_open, raising=False)

    # Stub web server start and broadcast
    import psd.web.server as web_server

    def fake_start(host: str = "127.0.0.1", port: int = 0, *, background: bool = True) -> tuple[str, int]:
        return host, 9001

    broadcasts = {"n": 0}

    def fake_broadcast(dto: dict) -> None:  # noqa: ARG001
        broadcasts["n"] += 1

    monkeypatch.setattr(web_server, "start", fake_start)
    monkeypatch.setattr(web_server, "broadcast", fake_broadcast)

    # Ensure IB positions are immediately available
    import psd.datasources.ibkr as ib

    monkeypatch.setattr(ib, "get_positions", lambda _cfg=None: [{"symbol": "SPY", "qty": 1}])

    # Run the starter with bounded loops
    from psd.runner import start_psd

    host, port = start_psd(loops=2, interval_override=0.001)

    assert host == "127.0.0.1"
    assert port == 9001
    # Two iterations should result in two broadcasts
    assert broadcasts["n"] == 2
    # Browser open was requested by defaults
    assert opened["n"] >= 1

