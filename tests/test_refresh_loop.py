# SPDX-License-Identifier: MIT

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from positions_engine.core.models import Instrument, InstrumentType, Position, Quote, TradingSession
from positions_engine.core.session import SessionInfo
from positions_engine.service import PositionsState, RefreshLoop


def test_refresh_loop_executes_tick() -> None:
    calls: list[float] = []
    ready = threading.Event()

    def tick() -> None:
        calls.append(time.monotonic())
        ready.set()

    loop = RefreshLoop(tick=tick, interval_s=0.05)
    loop.start()
    try:
        assert ready.wait(timeout=1.0)
        loop.stop()
    finally:
        loop.stop()
        thread = getattr(loop, "_thread", None)
        if thread is not None:
            thread.join(timeout=0.2)
    assert calls, "expected refresh loop to invoke tick at least once"


def test_refresh_live_snapshot_clears_positions_when_feed_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    state = PositionsState()

    instrument = Instrument(
        symbol="AAPL", instrument_type=InstrumentType.EQUITY, multiplier=Decimal("1")
    )
    position = Position(
        instrument=instrument,
        quantity=Decimal("5"),
        avg_cost=Decimal("100"),
    )
    state.refresh(positions=[position], quotes=[])
    initial_version = state._positions_version
    assert state._positions

    monkeypatch.setattr(
        "positions_engine.service.state.InternalScriptsProvider.load",
        lambda self: ([], []),
    )

    state.refresh_live_snapshot()

    assert state._positions == {}
    assert state._positions_version == initial_version + 1


def test_refresh_live_snapshot_preserves_positions_for_partial_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = PositionsState()

    aapl_instrument = Instrument(
        symbol="AAPL", instrument_type=InstrumentType.EQUITY, multiplier=Decimal("1")
    )
    msft_instrument = Instrument(
        symbol="MSFT", instrument_type=InstrumentType.EQUITY, multiplier=Decimal("1")
    )
    aapl_position = Position(
        instrument=aapl_instrument,
        quantity=Decimal("5"),
        avg_cost=Decimal("150"),
    )
    msft_position = Position(
        instrument=msft_instrument,
        quantity=Decimal("8"),
        avg_cost=Decimal("300"),
    )
    state.refresh(positions=[aapl_position, msft_position], quotes=[])

    positions_records = [
        {
            "symbol": "AAPL",
            "instrument_type": "equity",
            "quantity": "6",
            "avg_cost": "150",
        }
    ]

    monkeypatch.setattr(
        "positions_engine.service.state.InternalScriptsProvider.load",
        lambda self: (positions_records, []),
    )

    state.refresh_live_snapshot()

    assert set(state._positions.keys()) == {"AAPL", "MSFT"}
    assert state._positions["AAPL"].quantity == Decimal("6")
    assert state._positions["MSFT"].quantity == Decimal("8")


def test_refresh_live_snapshot_updates_latest_ts(monkeypatch: pytest.MonkeyPatch) -> None:
    state = PositionsState()

    equity_instrument = Instrument(
        symbol="AAPL", instrument_type=InstrumentType.EQUITY, multiplier=Decimal("1")
    )
    option_instrument = Instrument(
        symbol="AAPL 20240315C00150000",
        instrument_type=InstrumentType.OPTION,
        multiplier=Decimal("100"),
    )
    equity_position = Position(
        instrument=equity_instrument,
        quantity=Decimal("10"),
        avg_cost=Decimal("150"),
    )
    option_position = Position(
        instrument=option_instrument,
        quantity=Decimal("1"),
        avg_cost=Decimal("2.50"),
        metadata={
            "underlying": "AAPL",
            "expiry": "2024-03-15",
            "right": "CALL",
            "delta": Decimal("0.40"),
            "previous_close": Decimal("2.45"),
        },
    )

    base_time = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)
    equity_quote = Quote(
        symbol="AAPL",
        last=Decimal("150"),
        previous_close=Decimal("149"),
        last_ts=base_time - timedelta(minutes=1),
        updated_at=base_time - timedelta(minutes=1),
        session=TradingSession.RTH,
    )
    option_quote = Quote(
        symbol="AAPL 20240315C00150000",
        last=Decimal("2.55"),
        updated_at=base_time - timedelta(minutes=1),
        session=TradingSession.RTH,
    )
    state.refresh(
        positions=[equity_position, option_position],
        quotes=[equity_quote, option_quote],
        snapshot_at=base_time - timedelta(minutes=1),
        data_source="internal",
    )

    refresh_time = base_time + timedelta(minutes=2)
    positions_records = [
        {
            "symbol": "AAPL",
            "instrument_type": "equity",
            "quantity": "10",
            "avg_cost": "150",
        },
        {
            "symbol": "AAPL 20240315C00150000",
            "instrument_type": "option",
            "quantity": "1",
            "avg_cost": "2.50",
            "underlying": "AAPL",
            "expiry": "2024-03-15",
            "right": "CALL",
            "delta": "0.55",
        },
    ]
    quotes_records = [
        {
            "symbol": "AAPL",
            "bid": "151.00",
            "ask": "152.00",
            "last": "151.50",
            "updated_at": refresh_time.isoformat(),
            "bid_ts": refresh_time.isoformat(),
            "ask_ts": refresh_time.isoformat(),
        },
        {
            "symbol": "AAPL 20240315C00150000",
            "last": "2.65",
            "updated_at": refresh_time.isoformat(),
        },
    ]

    monkeypatch.setattr(
        "positions_engine.service.state.InternalScriptsProvider.load",
        lambda self: (positions_records, quotes_records),
    )

    session_as_of = (refresh_time + timedelta(seconds=30)).astimezone(timezone.utc)
    monkeypatch.setattr(
        "positions_engine.service.state.detect_session",
        lambda: SessionInfo(
            exchange="XNYS",
            tz="America/New_York",
            state="RTH",
            as_of=session_as_of.isoformat(),
        ),
    )

    state.refresh_live_snapshot()

    stats = state.stats()
    meta = stats.get("meta")
    assert isinstance(meta, dict)
    latest_ts = meta.get("latest_ts")
    assert latest_ts is not None
    parsed_latest = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))
    assert parsed_latest >= session_as_of

    live_seen = meta.get("live_seen")
    assert live_seen == {"quotes": 2, "greeks": 1}

    quotes_snapshot = state.quotes_snapshot()
    assert quotes_snapshot["AAPL"].last == Decimal("151.50")

def test_refresh_live_greeks_updates_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    state = PositionsState()
    option_instrument = Instrument(
        symbol="AAPL 20240315C00150000",
        instrument_type=InstrumentType.OPTION,
        multiplier=Decimal("100"),
    )
    option_position = Position(
        instrument=option_instrument,
        quantity=Decimal("1"),
        avg_cost=Decimal("2.50"),
        metadata={},
    )
    state.refresh(positions=[option_position], quotes=[])

    refresh_time = datetime(2024, 1, 2, 15, 5, tzinfo=UTC)
    greeks_payload = {
        "rows": [
            {
                "symbol": "AAPL 20240315C00150000",
                "delta": "0.62",
                "theta": "-0.03",
            }
        ],
        "as_of": refresh_time.isoformat(),
    }

    monkeypatch.setattr(
        "positions_engine.service.state.InternalScriptsProvider.load_greeks_snapshot",
        lambda self: greeks_payload,
    )

    state.refresh_live_greeks()

    updated = state._positions["AAPL 20240315C00150000"]
    assert updated.metadata.get("delta") == Decimal("0.62")
    assert updated.metadata.get("theta") == Decimal("-0.03")

    meta = state.stats()["meta"]
    assert meta["live_seen"]["greeks"] == 1
    assert meta["latest_ts"].startswith("2024-01-02T15:05:00")


def test_refresh_endpoint_triggers_state_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.api import main as api_main

    class DummyLoop:
        def start(self) -> None:  # pragma: no cover - simple stub
            pass

        def stop(self) -> None:  # pragma: no cover - simple stub
            pass

    monkeypatch.setattr(api_main, "_refresh_from_providers", lambda: None)
    monkeypatch.setattr(api_main, "refresh_loop", DummyLoop())

    calls: list[str] = []

    def fake_snapshot() -> None:
        calls.append("snapshot")

    def fake_greeks() -> None:
        calls.append("greeks")

    monkeypatch.setattr(api_main._state, "refresh_live_snapshot", fake_snapshot)
    monkeypatch.setattr(api_main._state, "refresh_live_greeks", fake_greeks)

    with TestClient(api_main.app) as client:
        response = client.post("/refresh")
        assert response.status_code == 200

    assert calls == ["snapshot", "greeks"]
