from __future__ import annotations

import asyncio

from portfolio_exporter import psd_adapter


class _FakeEngineState:
    def equities_payload(self) -> list[dict[str, object]]:
        return [
            {
                "symbol": "AAPL",
                "qty": 50,
                "avg_cost": 120.0,
                "mark": 125.5,
                "mark_source": "mid",
                "stale_seconds": 15,
                "day_pnl": 275.0,
            }
        ]

    def options_payload(self) -> dict[str, object]:
        return {
            "combos": [
                {
                    "combo_id": "combo-1",
                    "strategy": "VERTICAL",
                    "underlying": "TSLA",
                    "day_pnl_amount": 35.0,
                    "sum_greeks": {"delta": 9.5, "gamma": 0.4, "theta": -0.08},
                    "legs": [
                        {
                            "symbol": "TSLA 20240419C00750000",
                            "underlying": "TSLA",
                            "quantity": 1,
                            "avg_cost": 2.4,
                            "mark": 3.1,
                            "mark_source": "MID",
                            "stale_seconds": 18,
                            "delta": 0.52,
                            "gamma": 0.12,
                            "theta": -0.03,
                            "right": "CALL",
                            "strike": 750.0,
                            "expiry": "2024-04-19",
                            "multiplier": 100,
                            "day_pnl": 20.0,
                        },
                        {
                            "symbol": "TSLA 20240419C00760000",
                            "underlying": "TSLA",
                            "quantity": -1,
                            "avg_cost": 1.8,
                            "mark": 1.35,
                            "mark_source": "MID",
                            "stale_seconds": 20,
                            "delta": -0.41,
                            "gamma": -0.09,
                            "theta": -0.02,
                            "right": "CALL",
                            "strike": 760.0,
                            "expiry": "2024-04-19",
                            "multiplier": 100,
                            "day_pnl": 15.0,
                        },
                    ],
                }
            ],
            "legs": [
                {
                    "symbol": "MSFT 20240419P00250000",
                    "underlying": "MSFT",
                    "quantity": -1,
                    "avg_cost": 1.25,
                    "mark": 1.05,
                    "mark_source": "LAST",
                    "stale_seconds": 45,
                    "delta": -0.31,
                    "gamma": 0.02,
                    "theta": -0.015,
                    "right": "PUT",
                    "strike": 250.0,
                    "expiry": "2024-04-19",
                    "multiplier": 100,
                    "day_pnl": -6.0,
                }
            ],
        }


def test_snapshot_once_uses_engine_fallback(monkeypatch) -> None:
    async def _positions() -> list[dict[str, object]]:
        return []

    async def _marks(_positions: list[dict[str, object]]) -> dict[str, object]:
        return {}

    async def _greeks(_positions: list[dict[str, object]], _marks: dict[str, object]) -> dict[str, float]:
        return {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}

    async def _risk(
        _positions: list[dict[str, object]],
        _marks: dict[str, object],
        _greeks: dict[str, float],
    ) -> dict[str, float]:
        return {"beta": 0.0, "var95_1d": 0.0, "margin_pct": 0.0, "notional": 0.0}

    fake_state = _FakeEngineState()

    monkeypatch.setattr(psd_adapter, "load_positions", _positions)
    monkeypatch.setattr(psd_adapter, "get_marks", _marks)
    monkeypatch.setattr(psd_adapter, "compute_greeks", _greeks)
    monkeypatch.setattr(psd_adapter, "compute_risk", _risk)
    monkeypatch.setattr(
        psd_adapter,
        "split_positions",
        lambda _pos, _session: psd_adapter._empty_positions_view(),
    )
    psd_adapter._ENGINE_STATE_CACHE = psd_adapter._CACHE_SENTINEL
    monkeypatch.setattr(psd_adapter, "_get_positions_engine_state", lambda: fake_state)

    snapshot = asyncio.run(psd_adapter.snapshot_once())
    view = snapshot["positions_view"]

    assert view["single_stocks"], "fallback should populate single stocks"
    assert view["single_stocks"][0]["symbol"] == "AAPL"
    assert view["option_combos"], "fallback should populate combos"
    assert view["option_combos"][0]["legs"], "combo legs should not be empty"
    assert view["single_options"], "fallback should include orphan option legs"
    assert view["single_options"][0]["symbol"] == "MSFT"
