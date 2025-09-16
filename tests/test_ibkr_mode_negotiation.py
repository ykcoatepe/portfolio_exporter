from __future__ import annotations

from typing import List

from src.psd.datasources import ibkr


class _EntitlementError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"error {code}")
        self.errorCode = code


class _StubClient:
    def __init__(self) -> None:
        self.calls: List[int] = []
        self._first = True

    def reqMarketDataType(self, mode: int) -> bool:
        self.calls.append(mode)
        if self._first and mode == 1:
            self._first = False
            raise _EntitlementError(10167)
        return True


def test_auto_mode_falls_back_to_delayed_on_entitlement() -> None:
    client = _StubClient()
    mode = ibkr.set_market_data_mode("auto", client=client, timeout=0.05, has_ticks=lambda: True)
    assert mode == "delayed"
    assert client.calls == [1, 4]
    assert ibkr.is_entitlement_error(10167) is True
