from __future__ import annotations

import json
import urllib.request
from typing import Any


def post_message(token: str, channel: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Minimal Slack Web API client for chat.postMessage.

    Expects `payload` with at least 'channel' and either 'text' or 'blocks'.
    Returns parsed JSON; on success includes 'ok': True and 'ts'.
    """
    url = "https://slack.com/api/chat.postMessage"
    body = dict(payload)
    body.setdefault("channel", channel)
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # nosec - caller controls URL/token
        raw = resp.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"ok": False, "error": "invalid_json"}
