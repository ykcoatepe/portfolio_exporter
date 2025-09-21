# SPDX-License-Identifier: MIT

"""In-memory joiner for normalized position snapshots."""

from __future__ import annotations

import math
from collections.abc import Iterable
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any

from ..combos import (
    ComboDetection,
    OptionCombo,
    OptionLegSnapshot,
    build_leg_display,
    build_option_leg_snapshot,
    detect_option_combos,
    group_option_combos,
    strategy_label,
)
from ..core.marks import MarkResult, MarkSettings, select_equity_mark
from ..core.models import InstrumentType, Position, Quote, TradingSession
from ..core.pnl import equity_pnl


class PositionsState:
    """Cache positions + quotes and emit normalized equity payloads."""

    def __init__(self, mark_settings: MarkSettings | None = None) -> None:
        self._mark_settings = mark_settings or MarkSettings()
        self._positions: dict[str, Position] = {}
        self._quotes: dict[str, Quote] = {}
        self._positions_version = 0
        self._quotes_version = 0
        self._options_cache: dict[str, Any] | None = None
        self._positions_view: dict[str, Any] | None = None
        self._positions_view_raw: dict[str, Any] | None = None
        self._snapshot_override: datetime | None = None
        self._data_source: str = "unknown"

    def refresh(
        self,
        positions: Iterable[Position] | None = None,
        quotes: Iterable[Quote] | None = None,
        snapshot_at: datetime | None = None,
        data_source: str | None = None,
        positions_view: dict[str, Any] | None = None,
    ) -> None:
        fallback_needed = False
        if positions is not None:
            self._positions_version += 1
            self._positions = {p.instrument.symbol: p for p in positions}
            fallback_needed = positions_view is None
        if quotes is not None:
            self._quotes_version += 1
            self._quotes = {q.symbol: q for q in quotes}
            if self._positions_view is None and positions_view is None:
                fallback_needed = True
        if positions is not None or quotes is not None:
            self._options_cache = None
        if positions_view is not None:
            self._positions_view = _sanitize_positions_view(positions_view)
            self._positions_view_raw = deepcopy(positions_view)
            fallback_needed = False
        elif fallback_needed:
            fallback_view = self._build_positions_view(snapshot_at)
            self._positions_view = fallback_view
            self._positions_view_raw = deepcopy(fallback_view)
        if snapshot_at is not None:
            self._snapshot_override = _ensure_aware(snapshot_at)
        elif quotes is not None:
            self._snapshot_override = None
        if data_source is not None:
            self._data_source = data_source

    def snapshot_updated_at(self) -> datetime | None:
        """Return the freshest quote timestamp available, if any."""

        if self._snapshot_override is not None:
            return self._snapshot_override

        latest: datetime | None = None
        for quote in self._quotes.values():
            if quote.updated_at is None:
                continue
            candidate = _ensure_aware(quote.updated_at)
            if latest is None or candidate > latest:
                latest = candidate
        return latest

    def equities_payload(self, now: datetime | None = None) -> list[dict[str, Any]]:
        rows, _ = self._rows(now)
        return rows

    def options_payload(self, now: datetime | None = None) -> dict[str, Any]:
        detection, as_of = self._ensure_options_detection(now)
        grouping = group_option_combos(detection.combos)

        combos_payload: list[dict[str, Any]] = []
        for combo in detection.combos:
            payload = combo.to_payload()
            combo_id = payload.get("combo_id")
            if isinstance(combo_id, str):
                payload.setdefault("id", combo_id)
            extras = grouping.combo_extras.get(combo.combo_id)
            if extras:
                payload.update(extras)
            for leg_payload in payload.get("legs", []):
                leg_id = leg_payload.get("leg_id")
                if isinstance(leg_id, str):
                    leg_payload.setdefault("id", leg_id)
                    leg_extra = grouping.leg_extras.get(leg_id)
                    if leg_extra:
                        leg_payload.update(leg_extra)
            combos_payload.append(payload)

        legs_payload: list[dict[str, Any]] = []
        for leg in detection.orphans:
            payload = leg.to_payload()
            leg_id = payload.get("leg_id")
            if isinstance(leg_id, str):
                payload.setdefault("id", leg_id)
            leg_extra = grouping.leg_extras.get(leg.leg_id)
            if leg_extra:
                payload.update(leg_extra)
            else:
                display = build_leg_display(leg.underlying, leg.strike, leg.right, leg.expiry)
                payload["label"] = display.leg_label
                payload["display"] = {
                    "leg_label": display.leg_label,
                    "short_ul": display.short_ul,
                    "expiry_short": display.expiry_short,
                }
            legs_payload.append(payload)

        return {
            "as_of": _isoformat(as_of),
            "combos": combos_payload,
            "combo_groups": [group.to_payload() for group in grouping.groups],
            "legs": legs_payload,
        }

    def options_detection(self, now: datetime | None = None) -> ComboDetection:
        detection, _ = self._ensure_options_detection(now)
        return detection

    def stats(self, now: datetime | None = None) -> dict[str, int | float]:
        rows, stale = self._rows(now)
        detection, _ = self._ensure_options_detection(now)
        legs_count = sum(len(combo.legs) for combo in detection.combos) + len(detection.orphans)
        return {
            "equity_count": len(rows),
            "quote_count": len(self._quotes),
            "stale_quotes_count": stale,
            "option_legs_count": legs_count,
            "combos_matched": len(detection.combos),
            "combos_detection_ms": detection.detection_ms,
            "data_source": self._data_source,
        }

    @property
    def data_source(self) -> str:
        return self._data_source

    def positions_view_payload(self, now: datetime | None = None) -> dict[str, Any]:
        """Return the most recent positions_view, computing a fallback if needed."""

        if self._positions_view_raw is not None:
            return deepcopy(self._positions_view_raw)
        if self._positions_view is not None:
            return deepcopy(self._positions_view)
        return self._build_positions_view(now)

    def snapshot_payload(self, now: datetime | None = None) -> dict[str, Any]:
        """Return a PSD-style snapshot for /state consumers."""

        now = _ensure_aware(now)
        snapshot_at = self.snapshot_updated_at()
        ts = int(snapshot_at.timestamp() * 1000) if snapshot_at is not None else None
        positions_view = self.positions_view_payload(now)
        positions_dump = [position.model_dump(mode="json") for position in self._positions.values()]
        quotes_dump = {symbol: quote.model_dump(mode="json") for symbol, quote in self._quotes.items()}
        return {
            "ts": ts,
            "session": self._resolve_session(),
            "positions": positions_dump,
            "positions_view": positions_view,
            "quotes": quotes_dump,
            "risk": {},
            "data_source": self._data_source,
        }

    def _rows(self, now: datetime | None) -> tuple[list[dict[str, Any]], int]:
        now = _ensure_aware(now)
        rows: list[dict[str, Any]] = []
        stale = 0
        for symbol, position in sorted(self._positions.items()):
            if position.instrument.instrument_type != InstrumentType.EQUITY:
                continue
            quote = self._quotes.get(symbol)
            mark = select_equity_mark(quote, now, self._mark_settings)
            mark_value = _mark_or_fallback(mark, position)
            if mark.is_stale:
                stale += 1
            prev_close = quote.previous_close if quote else None
            pnl = equity_pnl(position, mark.mark, prev_close)
            day_basis = _day_basis(position, prev_close)
            total_basis = _total_basis(position)
            rows.append(
                {
                    "symbol": symbol,
                    "qty": float(position.quantity),
                    "avg_cost": float(position.avg_cost),
                    "mark": float(mark_value),
                    "mark_source": mark.source,
                    "day_pnl": float(pnl.day),
                    "day_pnl_percent": _maybe_float(_percent(pnl.day, day_basis)),
                    "total_pnl": float(pnl.total),
                    "total_pnl_percent": _maybe_float(_percent(pnl.total, total_basis)),
                    "stale_seconds": mark.stale_seconds,
                }
            )
        return rows, stale

    def _build_positions_view(self, now: datetime | None) -> dict[str, Any]:
        now = _ensure_aware(now)
        equities_view = [_equity_view_from_row(row) for row in self.equities_payload(now)]
        detection, _ = self._ensure_options_detection(now)
        combos_view = [_combo_view_from_detection(combo) for combo in detection.combos]
        single_options_view = [_option_leg_view_from_detection(leg) for leg in detection.orphans]
        return {
            "single_stocks": equities_view,
            "option_combos": combos_view,
            "single_options": single_options_view,
        }

    def _resolve_session(self) -> str:
        for quote in self._quotes.values():
            session = quote.session
            if isinstance(session, TradingSession):
                return session.value
            if isinstance(session, str) and session:
                return session
        return TradingSession.CLOSED.value

    def _ensure_options_detection(self, now: datetime | None) -> tuple[ComboDetection, datetime]:
        now = _ensure_aware(now)
        cache = self._options_cache or {}
        cache_day = now.date()
        if (
            cache
            and cache.get("positions_version") == self._positions_version
            and cache.get("quotes_version") == self._quotes_version
            and cache.get("day") == cache_day
        ):
            detection = cache["detection"]
        else:
            legs = []
            for position in self._positions.values():
                leg = build_option_leg_snapshot(
                    position,
                    self._quotes.get(position.instrument.symbol),
                    now,
                    self._mark_settings,
                )
                if leg is not None:
                    legs.append(leg)
            detection = detect_option_combos(legs)
            self._options_cache = {
                "positions_version": self._positions_version,
                "quotes_version": self._quotes_version,
                "day": cache_day,
                "detection": detection,
            }
        return detection, now


def _sanitize_positions_view(view: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key in ("single_stocks", "option_combos", "single_options"):
        sanitized[key] = []
        raw = view.get(key)
        if isinstance(raw, list):
            if key == "option_combos":
                sanitized[key] = [_sanitize_combo_entry(entry) for entry in raw if isinstance(entry, dict)]
            else:
                sanitized[key] = [deepcopy(entry) for entry in raw if isinstance(entry, dict)]
    for key, value in view.items():
        if key not in sanitized:
            try:
                sanitized[key] = deepcopy(value)
            except Exception:  # pragma: no cover - fallback for non-copyable values
                sanitized[key] = value
    return sanitized


def _sanitize_combo_entry(entry: dict[str, Any]) -> dict[str, Any]:
    combo = deepcopy(entry)
    legs = combo.get("legs")
    if isinstance(legs, list):
        combo["legs"] = [deepcopy(leg) for leg in legs if isinstance(leg, dict)]
    else:
        combo["legs"] = []
    return combo


def _equity_view_from_row(row: dict[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").strip()
    qty = _to_float(row.get("qty"))
    avg_cost = _to_float(row.get("avg_cost"))
    mark = _to_float(row.get("mark"))
    return {
        "secType": "STK",
        "symbol": symbol,
        "qty": qty if qty is not None else 0.0,
        "avg_cost": avg_cost,
        "multiplier": 1,
        "mark": mark,
        "mark_source": row.get("mark_source"),
        "price_source": _safe_lower(row.get("mark_source")) or row.get("mark_source"),
        "stale_s": _to_int(row.get("stale_seconds")),
        "pnl_intraday": _to_float(row.get("day_pnl")),
        "pnl_unrealized": _to_float(row.get("total_pnl")),
        "greeks": {"delta": None, "gamma": None, "theta": None},
        "previous_close": _to_float(row.get("previous_close")),
    }


def _combo_view_from_detection(combo: OptionCombo) -> dict[str, Any]:
    legs = [_option_leg_view_from_detection(leg) for leg in combo.legs]
    return {
        "combo_id": combo.combo_id,
        "name": strategy_label(combo.strategy),
        "strategy": combo.strategy.value,
        "underlier": combo.underlying,
        "account": combo.account,
        "dte": combo.dte,
        "net_price": _to_float(combo.net_price),
        "pnl_intraday": _to_float(combo.day_pnl),
        "pnl_unrealized": _to_float(combo.total_pnl),
        "greeks_agg": {
            "delta": _to_float(combo.sum_delta),
            "gamma": _to_float(combo.sum_gamma),
            "theta": _to_float(combo.sum_theta),
            "vega": _to_float(combo.sum_vega),
        },
        "legs": legs,
        "notes": list(combo.notes),
    }


def _option_leg_view_from_detection(leg: OptionLegSnapshot) -> dict[str, Any]:
    qty = _to_float(leg.quantity)
    avg_cost = _to_float(leg.avg_cost)
    mark = _to_float(leg.mark)
    return {
        "secType": "OPT",
        "symbol": leg.instrument_symbol,
        "underlying": leg.underlying,
        "qty": qty if qty is not None else 0.0,
        "avg_cost": avg_cost,
        "multiplier": _to_float(leg.multiplier),
        "mark": mark,
        "mark_source": leg.mark_source,
        "price_source": _safe_lower(leg.mark_source) or leg.mark_source,
        "stale_s": leg.stale_seconds,
        "pnl_intraday": _to_float(leg.day_pnl),
        "pnl_unrealized": _to_float(leg.total_pnl),
        "greeks": {
            "delta": _to_float(leg.delta),
            "gamma": _to_float(leg.gamma),
            "theta": _to_float(leg.theta),
            "vega": _to_float(leg.vega),
        },
        "right": leg.right,
        "strike": _to_float(leg.strike),
        "expiry": leg.expiry,
        "ratio": _to_float(leg.ratio),
        "leg_id": leg.leg_id,
        "account": leg.account,
        "notes": list(leg.notes),
        "previous_close": _to_float(leg.previous_close),
        "conId": None,
    }


def _safe_lower(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text.lower()
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return result


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return int(number)


def _day_basis(position: Position, previous_close: Decimal | None) -> Decimal | None:
    if previous_close is None:
        return None
    return previous_close * position.quantity * position.multiplier


def _total_basis(position: Position) -> Decimal | None:
    return position.avg_cost * position.quantity * position.multiplier


def _percent(numerator: Decimal, basis: Decimal | None) -> Decimal | None:
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


def _maybe_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _mark_or_fallback(mark: MarkResult, position: Position) -> Decimal:
    return Decimal(mark.mark) if mark.mark is not None else position.avg_cost


def _ensure_aware(ts: datetime | None) -> datetime:
    if ts is None:
        return datetime.now(tz=UTC)
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _isoformat(ts: datetime) -> str:
    ts = _ensure_aware(ts)
    text = ts.isoformat()
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text
