# SPDX-License-Identifier: MIT

"""Core Pydantic models for the positions engine."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InstrumentType(str, Enum):
    """Supported asset classes for downstream consumers."""

    EQUITY = "equity"
    OPTION = "option"
    FUTURE = "future"


class TradingSession(str, Enum):
    """Trading-session buckets used across quote ingestion."""

    RTH = "RTH"
    ETH = "ETH"
    CLOSED = "CLOSED"


class Instrument(BaseModel):
    """Basic instrument description."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    symbol: str
    instrument_type: InstrumentType = InstrumentType.EQUITY
    description: str | None = None
    currency: str = "USD"
    multiplier: Decimal = Decimal("1")


class Position(BaseModel):
    """Open position values normalized for analytics."""

    model_config = ConfigDict(frozen=True)

    instrument: Instrument
    quantity: Decimal
    avg_cost: Decimal
    cost_basis: Decimal | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def multiplier(self) -> Decimal:
        return self.instrument.multiplier


class Quote(BaseModel):
    """Quote snapshot for an instrument."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    previous_close: Decimal | None = None
    session: TradingSession = TradingSession.CLOSED
    updated_at: datetime | None = None
    extended_last: Decimal | None = None

    @property
    def mid(self) -> Decimal | None:
        if self.bid is None or self.ask is None:
            return None
        if self.bid <= Decimal("0") or self.ask <= Decimal("0"):
            return None
        return (self.bid + self.ask) / Decimal("2")


class Greeks(BaseModel):
    """Option greeks placeholder to keep schema parity with downstream spec."""

    model_config = ConfigDict(frozen=True)

    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
