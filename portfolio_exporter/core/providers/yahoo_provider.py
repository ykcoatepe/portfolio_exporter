from __future__ import annotations

from typing import Any, Dict, List


def fetch_quote(_symbol: str) -> Dict[str, Any]:
    # v1.1 will implement; v1 keeps offline CSV-only mode
    return {}


def fetch_chain(_symbol: str, _expiry: str | None = None) -> List[Dict[str, Any]]:
    # v1.1 will implement; v1 keeps offline CSV-only mode
    return []

