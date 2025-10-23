from __future__ import annotations

import json

import anyio
from httpx import ASGITransport, AsyncClient

import psd.web.app as web_app
from psd.web.config import Settings


def test_broadcast_latest_msb_emits_event(monkeypatch):
    sample = {
        "date": "2024-01-10",
        "hy": 1.25,
        "vx1": 16.0,
        "vx2": 17.0,
        "z_hy": 0.42,
        "term_ratio": 1.05,
        "cal_spread_pct": 0.03,
        "cal_spread_abs": 0.6,
        "saturated": False,
        "hy_score": 2,
        "vix_score": 3,
        "msb": 12,
        "color": "yellow",
        "triggers": ["cooldown"],
        "winsor_clipped_n": 0,
        "cooldown_until": None,
    }

    monkeypatch.setattr(web_app, "read_msb_current", lambda: sample)
    app = web_app.create_app(
        Settings(test_mode=True, disable_background=True, sse_heartbeat_sec=1)
    )

    async def _collect_event() -> dict[str, object]:
        response_holder: dict[str, object] = {}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:

            async def issue_request() -> None:
                response_holder["resp"] = await client.get(
                    "/sse", params={"test_once": "1"}, timeout=None
                )

            async with anyio.create_task_group() as tg:
                tg.start_soon(issue_request)
                await anyio.sleep(0.05)
                assert web_app.broadcast_latest_msb(app) is True

        resp = response_holder.get("resp")
        assert resp is not None
        body = resp.text.splitlines()
        current_event: str | None = None
        data_lines: list[str] = []
        payload: dict[str, object] | None = None
        for line in body:
            if line.startswith("event:"):
                current_event = line[6:].strip()
                data_lines = []
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif line.strip() == "":
                if current_event == "msb.update":
                    payload = json.loads("\n".join(data_lines) or "{}")
                    break
                current_event = None
                data_lines = []
        assert payload is not None
        return payload

    payload = anyio.run(_collect_event)
    assert payload["msb"] == sample["msb"]
    assert payload["triggers"] == sample["triggers"]
    serialized = json.dumps(payload, separators=(",", ":"))
    assert len(serialized.encode("utf-8")) <= 1024


def test_create_app_initializes_store_when_background_disabled(monkeypatch):
    calls: list[str] = []

    def fake_init() -> None:
        calls.append("init")

    monkeypatch.setattr(web_app, "init", fake_init)
    web_app.create_app(Settings(disable_background=True))

    assert calls == ["init"]
