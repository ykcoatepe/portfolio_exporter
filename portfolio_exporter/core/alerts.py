from __future__ import annotations

from typing import Any, Dict, List, Optional


def emit_alerts(
    alerts: List[Dict[str, Any]], webhook_url: Optional[str], dry_run: bool, offline: bool
) -> Dict[str, Any]:
    """POST alerts to webhook_url unless dry_run or offline; return {"sent":N,"failed":[...]}.

    Network use is disabled when dry_run or offline is True. Minimal timeout and
    no retries; caller should handle failures.
    """
    result: Dict[str, Any] = {"sent": 0, "failed": []}
    if not webhook_url or dry_run or offline or not alerts:
        return result
    try:
        import json
        import urllib.request

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

