from __future__ import annotations

from typing import Any


def emit_alerts(
    alerts: list[dict[str, Any]],
    webhook_url: str | None,
    dry_run: bool,
    offline: bool,
    per_item: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST alerts to webhook_url unless dry_run or offline; return {"sent":N,"failed":[...]}.

    Network use is disabled when dry_run or offline is True. Minimal timeout and
    no retries; caller should handle failures.
    """
    result: dict[str, Any] = {"sent": 0, "failed": []}
    if not webhook_url or dry_run or offline or not alerts:
        return result
    try:
        import json
        import urllib.request

        if per_item or extra:
            for a in alerts:
                payload = dict(a)
                if extra:
                    payload.update(extra)
                req = urllib.request.Request(
                    webhook_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:  # nosec - caller controls URL
                    if 200 <= resp.status < 300:
                        result["sent"] += 1
                    else:
                        result["failed"].append("http_status_" + str(resp.status))
        else:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(alerts).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:  # nosec - caller controls URL
                if 200 <= resp.status < 300:
                    result["sent"] = len(alerts)
                else:
                    result["failed"] = ["http_status_" + str(resp.status)]
    except Exception as exc:  # pragma: no cover - exercised via monkeypatch
        result["failed"] = [str(exc)]
    return result
