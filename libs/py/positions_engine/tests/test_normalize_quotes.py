from __future__ import annotations

from datetime import UTC, datetime

from positions_engine.service.normalize import quotes_from_records


def test_quotes_from_records_supports_epoch_seconds() -> None:
    quotes = quotes_from_records([
        {"symbol": "AAPL", "bid": 1.0, "ask": 1.1, "ts": 1_700_000_000},
    ])
    assert quotes[0].updated_at == datetime.fromtimestamp(1_700_000_000, tz=UTC)


def test_quotes_from_records_supports_iso_z() -> None:
    quotes = quotes_from_records([
        {"symbol": "MSFT", "bid": 1.0, "ask": 1.1, "quote_ts": "2024-01-02T12:00:00Z"},
    ])
    assert quotes[0].updated_at == datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


def test_quotes_from_records_supports_millisecond_strings() -> None:
    quotes = quotes_from_records([
        {"symbol": "SPY", "bid": 1.0, "ask": 1.1, "timestamp": "1700000000000"},
    ])
    assert quotes[0].updated_at == datetime.fromtimestamp(1_700_000_000, tz=UTC)


def test_quotes_from_records_reads_nested_tick_timestamp() -> None:
    quotes = quotes_from_records([
        {"symbol": "QQQ", "bid": 1.0, "ask": 1.1, "tick": {"ts": 1_700_000_100}},
    ])
    assert quotes[0].updated_at == datetime.fromtimestamp(1_700_000_100, tz=UTC)
