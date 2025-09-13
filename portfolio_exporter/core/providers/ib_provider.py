from __future__ import annotations

from typing import Any, Dict, List


def fetch_quote(_symbol: str) -> Dict[str, Any]:
    raise NotImplementedError("IBKR provider wiring will arrive in v1.1")


def fetch_chain(_symbol: str, _expiry: str | None = None) -> List[Dict[str, Any]]:
    raise NotImplementedError("IBKR provider wiring will arrive in v1.1")

