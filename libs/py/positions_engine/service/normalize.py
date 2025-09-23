# SPDX-License-Identifier: MIT

"""Helpers to turn raw records into models for the positions engine."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any

from ..core.models import Instrument, InstrumentType, Position, Quote, TradingSession


def positions_from_records(records: Iterable[dict[str, Any]]) -> list[Position]:
    out: list[Position] = []
    for row in records:
        symbol = _resolve_symbol(row)
        if not symbol:
            continue
        raw_type = row.get("instrument_type") or row.get("secType") or "equity"
        inst_type = _safe_instrument_type(str(raw_type))
        instrument = Instrument(
            symbol=symbol,
            instrument_type=inst_type,
            description=row.get("description"),
            currency=str(row.get("currency", "USD")),
            multiplier=Decimal(str(row.get("multiplier", 1))),
        )
        metadata = _extract_metadata(row, inst_type)
        out.append(
            Position(
                instrument=instrument,
                quantity=Decimal(
                    str(row.get("quantity", row.get("qty", row.get("position", 0))))
                ),
                avg_cost=Decimal(
                    str(
                        row.get(
                            "avg_cost", row.get("average_cost", row.get("avgCost", 0))
                        )
                    )
                ),
                cost_basis=_to_decimal(row.get("cost_basis")),
                metadata=metadata,
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
                bid_ts=_extract_bid_timestamp(row),
                ask=_to_decimal(row.get("ask")),
                ask_ts=_extract_ask_timestamp(row),
                last=_to_decimal(row.get("last", row.get("close"))),
                last_ts=_extract_last_timestamp(row),
                previous_close=_to_decimal(
                    row.get("previous_close", row.get("priorClose"))
                ),
                previous_close_ts=_extract_previous_close_timestamp(row),
                session=_safe_session(
                    str(row.get("session", TradingSession.CLOSED.value))
                ),
                updated_at=_extract_quote_timestamp(row),
                extended_last=_to_decimal(row.get("extended_last")),
            )
        )
    return out

_TIMESTAMP_CONTAINER_KEYS: tuple[str, ...] = ("tick", "quote", "mark")


def _extract_timestamp_field(
    row: dict[str, Any], candidates: tuple[str, ...]
) -> datetime | None:
    for key in candidates:
        if key in row:
            ts = _parse_timestamp(row.get(key))
            if ts is not None:
                return ts

    for nested_key in _TIMESTAMP_CONTAINER_KEYS:
        nested = row.get(nested_key)
        if isinstance(nested, dict):
            for key in candidates:
                ts = _parse_timestamp(nested.get(key))
                if ts is not None:
                    return ts

    return None


def _extract_quote_timestamp(row: dict[str, Any]) -> datetime | None:
    return _extract_timestamp_field(
        row,
        (
            "updated_at",
            "updatedAt",
            "quote_ts",
            "quote_timestamp",
            "quoteTimestamp",
            "timestamp",
            "ts",
            "last_update",
            "last_updated",
            "lastUpdate",
            "lastUpdated",
            "as_of",
            "asOf",
        ),
    )


def _extract_previous_close_timestamp(row: dict[str, Any]) -> datetime | None:
    return _extract_timestamp_field(
        row,
        (
            "previous_close_ts",
            "previousCloseTs",
            "prior_close_ts",
            "priorCloseTs",
            "prev_close_ts",
            "prevCloseTs",
            "previous_close_at",
            "previousCloseAt",
            "prior_close_at",
            "priorCloseAt",
            "prev_close_at",
            "prevCloseAt",
        ),
    )


def _extract_bid_timestamp(row: dict[str, Any]) -> datetime | None:
    return _extract_timestamp_field(
        row,
        (
            "bid_ts",
            "bidTs",
            "bid_timestamp",
            "bidTimestamp",
            "bid_time",
            "bidTime",
            "bid_quote_time",
            "bidQuoteTime",
        ),
    )


def _extract_ask_timestamp(row: dict[str, Any]) -> datetime | None:
    return _extract_timestamp_field(
        row,
        (
            "ask_ts",
            "askTs",
            "ask_timestamp",
            "askTimestamp",
            "ask_time",
            "askTime",
            "ask_quote_time",
            "askQuoteTime",
        ),
    )


def _extract_last_timestamp(row: dict[str, Any]) -> datetime | None:
    return _extract_timestamp_field(
        row,
        (
            "last_ts",
            "lastTs",
            "last_timestamp",
            "lastTimestamp",
            "last_trade_ts",
            "lastTradeTs",
            "last_trade_timestamp",
            "lastTradeTimestamp",
            "last_trade_time",
            "lastTradeTime",
            "last_time",
            "lastTime",
            "trade_timestamp",
            "tradeTimestamp",
            "trade_ts",
        ),
    )



def _resolve_symbol(row: dict[str, Any]) -> str | None:
    for key in ("symbol", "ticker", "underlying_symbol", "conIdSymbol"):
        value = row.get(key)
        if value in (None, ""):
            continue
        symbol = str(value).strip()
        if symbol:
            return symbol
    return None


def _extract_metadata(row: dict[str, Any], inst_type: InstrumentType) -> dict[str, Any]:
    metadata: dict[str, Any] = {}

    def _get_value(*keys: str) -> Any:
        for key in keys:
            if key in row:
                value = row[key]
                if value not in (None, ""):
                    return value
        return None

    account = _get_value("account", "Account", "acct", "AccountName")
    if account is not None:
        metadata["account"] = str(account).strip()

    if inst_type == InstrumentType.OPTION:
        underlying = _get_value("underlying", "Underlying", "ticker", "root", "symbol")
        if underlying is not None:
            metadata["underlying"] = str(underlying).strip()
        expiry = _get_value(
            "expiry",
            "expiration",
            "maturity",
            "lastTradeDateOrContractMonth",
            "expiryDate",
        )
        if expiry is not None:
            metadata["expiry"] = str(expiry).strip()
        right = _normalize_right(
            _get_value("right", "option_right", "call_put", "cp", "optionRight", "side")
        )
        if right is not None:
            metadata["right"] = right
        strike = _get_value("strike", "option_strike", "strike_price", "strikePrice")
        if strike is not None:
            metadata["strike"] = _to_decimal(strike)
        ratio = _get_value("ratio", "leg_ratio", "ratioQuantity")
        if ratio is not None:
            metadata["ratio"] = _to_decimal(ratio)
        strategy_id = _get_value("strategy_id", "StrategyId", "ib_strategy_id")
        if strategy_id is not None:
            metadata["strategy_id"] = str(strategy_id).strip()
        combo_id = _get_value("combo_id", "ComboId", "comboUid")
        if combo_id is not None:
            metadata["combo_id"] = str(combo_id).strip()

    previous_close = _get_value(
        "previous_close", "prior_close", "prev_close", "prevClose"
    )
    if previous_close is not None:
        metadata["previous_close"] = _to_decimal(previous_close)

    for greek in ("delta", "gamma", "theta", "vega"):
        value = _get_value(greek, greek.upper(), f"option_{greek}")
        if value is not None:
            metadata[greek] = _to_decimal(value)

    iv_value = _get_value("iv", "IV", "implied_vol", "implied_volatility")
    if iv_value is not None:
        metadata["iv"] = _to_decimal(iv_value)

    combo_legs = _get_value("combo_legs")
    if combo_legs is not None:
        parsed = _parse_combo_legs(combo_legs)
        if parsed:
            metadata["combo_legs"] = parsed

    return metadata


def _parse_combo_legs(raw: Any) -> list[dict[str, Any]] | None:
    if isinstance(raw, list):
        return [entry for entry in raw if isinstance(entry, dict)] or None
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(decoded, list):
            return [entry for entry in decoded if isinstance(entry, dict)] or None
    return None


def _normalize_right(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in {"CALL", "C", "CALLS"}:
        return "CALL"
    if text in {"PUT", "P", "PUTS"}:
        return "PUT"
    return None


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


def compute_equity_pnl_fields(
    position: Position,
    mark: Decimal | None,
    previous_close: Decimal | None,
) -> dict[str, float | None]:
    """Compute realized metrics for an equity position row."""

    multiplier = position.instrument.multiplier
    quantity = position.quantity

    day_pnl_float: float | None = None
    day_percent_float: float | None = None
    if (
        mark is not None
        and previous_close is not None
        and quantity is not None
    ):
        day_basis = previous_close * quantity * multiplier
        day_pnl = (mark - previous_close) * quantity * multiplier
        day_pnl_float = float(day_pnl)
        day_percent = _percent_decimal(day_pnl, day_basis)
        day_percent_float = _decimal_to_float(day_percent)

    total_pnl_float: float | None = None
    total_percent_float: float | None = None
    if (
        mark is not None
        and position.avg_cost is not None
        and position.avg_cost != 0
        and quantity is not None
    ):
        total_basis = position.avg_cost * quantity * multiplier
        total_pnl = (mark - position.avg_cost) * quantity * multiplier
        total_pnl_float = float(total_pnl)
        total_percent = _percent_decimal(total_pnl, total_basis)
        total_percent_float = _decimal_to_float(total_percent)

    return {
        "day_pnl": day_pnl_float,
        "day_pnl_percent": day_percent_float,
        "day_pnl_pct": day_percent_float,
        "pnl_unrealized": total_pnl_float,
        "pnl_unrealized_percent": total_percent_float,
        "pnl_unrealized_pct": total_percent_float,
        "total_pnl": total_pnl_float,
        "total_pnl_percent": total_percent_float,
    }


def _percent_decimal(numerator: Decimal, basis: Decimal | None) -> Decimal | None:
    if basis is None:
        return None
    if basis == 0:
        return None
    denominator = abs(basis)
    if denominator == 0:
        return None
    try:
        return (numerator / denominator) * Decimal("100")
    except (DivisionByZero, InvalidOperation):
        return None


def _decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    result = float(value)
    if math.isnan(result):
        return None
    return result


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    seconds: float | None = None

    if isinstance(value, (int, float)):
        seconds = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z") or text.endswith("z"):
            text = text[:-1] + "+00:00"
        try:
            seconds = float(text)
        except (TypeError, ValueError):
            seconds = None
        else:
            if math.isnan(seconds):
                seconds = None
    if seconds is not None:
        if seconds > 1e12:
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None

    if not isinstance(value, str):
        value = str(value)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
