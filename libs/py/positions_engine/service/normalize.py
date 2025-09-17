# SPDX-License-Identifier: MIT

"""Helpers to turn raw records into models for the positions engine."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from ..core.models import Instrument, InstrumentType, Position, Quote, TradingSession


def positions_from_records(records: Iterable[dict[str, Any]]) -> list[Position]:
    out: list[Position] = []
    for row in records:
        symbol = row.get("symbol")
        if not symbol:
            continue
        inst_type = _safe_instrument_type(row.get("instrument_type", "equity"))
        instrument = Instrument(
            symbol=symbol,
            instrument_type=inst_type,
            description=row.get("description"),
            currency=str(row.get("currency", "USD")),
            multiplier=Decimal(str(row.get("multiplier", 1))),
        )
        out.append(
            Position(
                instrument=instrument,
                quantity=Decimal(str(row.get("quantity", row.get("qty", 0)))),
                avg_cost=Decimal(str(row.get("avg_cost", row.get("average_cost", 0)))),
                cost_basis=_to_decimal(row.get("cost_basis")),
            )
        )
    return out


def quotes_from_records(records: Iterable[dict[str, Any]]) -> list[Quote]:
    out: list[Quote] = []
    for row in records:
        symbol = row.get("symbol")
        if not symbol:
            continue
        out.append(
            Quote(
                symbol=symbol,
                bid=_to_decimal(row.get("bid")),
                ask=_to_decimal(row.get("ask")),
                last=_to_decimal(row.get("last", row.get("close"))),
                previous_close=_to_decimal(row.get("previous_close", row.get("priorClose"))),
                session=_safe_session(str(row.get("session", TradingSession.CLOSED.value))),
                updated_at=_parse_timestamp(row.get("updated_at")),
                extended_last=_to_decimal(row.get("extended_last")),
            )
        )
    return out


def _safe_instrument_type(value: str) -> InstrumentType:
    prefix = value.lower()
    if prefix.startswith("opt"):
        return InstrumentType.OPTION
    if prefix.startswith("fut"):
        return InstrumentType.FUTURE
    return InstrumentType.EQUITY


def _safe_session(value: str) -> TradingSession:
    try:
        return TradingSession(value)
    except ValueError:
        upper = value.upper()
        return TradingSession.__members__.get(upper, TradingSession.CLOSED)


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value), tz=UTC)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
