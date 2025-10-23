from __future__ import annotations

import os
from math import isfinite
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from psd.core.store import latest_health, latest_snapshot

_DEFAULT_MAX_AGE = 15.0
router = APIRouter()


def _resolve_max_age() -> float:
    raw = os.getenv("PSD_READY_MAX_AGE", "").strip()
    if not raw:
        return _DEFAULT_MAX_AGE
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_MAX_AGE
    return max(0.0, value)


def _coerce_age(value: Any) -> float | None:
    try:
        age = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(age) or age < 0:
        return None
    return age


def _unavailable(reason: str, age: float | None) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "reason": reason, "data_age_s": age},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/ready", include_in_schema=False)
def ready() -> JSONResponse:
    threshold = _resolve_max_age()

    snapshot = latest_snapshot()
    if not snapshot:
        return _unavailable("snapshot unavailable", None)

    health = latest_health()
    if not health:
        return _unavailable("health unavailable", None)

    age = _coerce_age(health.get("data_age_s"))
    if age is None:
        return _unavailable("missing or invalid data age", None)

    if age > threshold:
        return _unavailable(
            f"stale data ({age:.2f}s > {threshold:.2f}s)",
            age,
        )

    return JSONResponse(
        {
            "ok": True,
            "data_age_s": age,
            "threshold_s": threshold,
            "ibkr_connected": bool(health.get("ibkr_connected")),
            "snapshot_ts": snapshot.get("ts"),
            "health_ts": health.get("ts"),
        },
        status_code=status.HTTP_200_OK,
        headers={"Cache-Control": "no-store"},
    )
