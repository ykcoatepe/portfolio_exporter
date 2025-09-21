from __future__ import annotations

import json
from typing import Any, Dict, List


def test_run_loop_web_broadcast(monkeypatch: Any) -> None:
    # Capture payloads via a simple list
    captured: List[Dict[str, Any]] = []

    def capture(payload: Dict[str, Any]) -> None:
        # Ensure it's a dict and JSON-serializable
        assert isinstance(payload, dict)
        json.dumps(payload)
        captured.append(payload)

    # Optional: monkeypatch the server.broadcast to our capture (not required, but validates import path)
    try:
        import src.psd.web.server as web_server

        monkeypatch.setattr(web_server, "broadcast", capture, raising=False)
    except Exception:
        # Server may be unavailable in minimal envs; ignore
        pass

    from src.psd.sentinel import sched

    # Run two quick iterations with no file writes
    sched.run_loop(interval=0.01, cfg={"memo_path": ""}, loops=2, web_broadcast=capture)

    assert len(captured) == 2
    # Ensure each payload can be serialized by the caller as well
    for dto in captured:
        assert isinstance(dto, dict)
        json.dumps(dto)

