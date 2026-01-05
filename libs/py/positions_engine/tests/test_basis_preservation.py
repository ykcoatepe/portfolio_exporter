# SPDX-License-Identifier: MIT

"""Regression to ensure avg_cost remains stable across snapshot gaps."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from positions_engine.ingest.internal import InternalScriptsProvider
from positions_engine.service.normalize import (
    compute_equity_pnl_fields,
    positions_from_records,
)
from positions_engine.service.state import PositionsState


def test_live_refresh_preserves_avg_cost_when_snapshot_omits_basis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = InternalScriptsProvider()

    snapshot_with_basis = {
        "positions_view": {
            "single_stocks": [
                {
                    "symbol": "AAPL",
                    "qty": 10,
                    "avg_cost": "123.45",
                    "mark": "130",
                }
            ],
            "option_combos": [],
            "single_options": [],
        },
        "positions": [
            {
                "symbol": "AAPL",
                "instrument_type": "equity",
                "quantity": 10,
                "avg_cost": "123.45",
            }
        ],
        "quotes": [],
    }
    initial_records, _ = provider._normalize_snapshot(snapshot_with_basis)
    initial_positions = positions_from_records(initial_records)

    now = datetime.now(tz=UTC)
    state = PositionsState()
    state.refresh(positions=initial_positions, quotes=[], snapshot_at=now)
    assert state._positions["AAPL"].avg_cost == Decimal("123.45")

    snapshot_missing_basis = {
        "positions_view": {
            "single_stocks": [
                {
                    "symbol": "AAPL",
                    "qty": 10,
                    "mark": "131",
                }
            ],
            "option_combos": [],
            "single_options": [],
        },
        "positions": [],
        "quotes": [],
    }
    missing_records, missing_quotes = provider._normalize_snapshot(
        snapshot_missing_basis
    )
    assert missing_records and missing_records[0]["avg_cost"] is None

    monkeypatch.setattr(
        InternalScriptsProvider,
        "load",
        lambda self: (missing_records, missing_quotes),
    )

    state.refresh_live_snapshot()

    updated = state._positions["AAPL"]
    assert updated.avg_cost == Decimal("123.45")

    totals = compute_equity_pnl_fields(
        position=updated,
        mark=Decimal("132"),
        previous_close=Decimal("128"),
    )
    assert totals["total_pnl"] == pytest.approx(85.5)
