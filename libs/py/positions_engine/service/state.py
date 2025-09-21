# SPDX-License-Identifier: MIT

"""In-memory joiner for normalized position snapshots."""

from __future__ import annotations

import logging
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
from ..combos.eval import evaluate_playbook_targets
from ..core.marks import MarkResult, MarkSettings, select_equity_mark
from ..core.models import InstrumentType, Position, Quote, TradingSession
from ..core.pnl import equity_pnl


logger = logging.getLogger(__name__)


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
        self._upstream_view_fallback_logged = False
        self._upstream_view_missing_combos_logged = False
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
            sanitized_view = _sanitize_positions_view(positions_view)
            self._positions_view = sanitized_view
            self._positions_view_raw = deepcopy(positions_view)
            if _positions_view_has_rows(sanitized_view):
                self._upstream_view_fallback_logged = False
                self._upstream_view_missing_combos_logged = False
            fallback_needed = False
        elif fallback_needed:
            fallback_view = self.build_fallback_positions_view(snapshot_at)
            self._positions_view = fallback_view
            self._positions_view_raw = None
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
        combo_groups_payload = [group.to_payload() for group in grouping.groups]
        group_lookup = {
            payload["combo_group_id"]: payload
            for payload in combo_groups_payload
            if isinstance(payload, dict) and isinstance(payload.get("combo_group_id"), str)
        }

        evaluation = evaluate_playbook_targets(detection.combos, detection.orphans, self._quotes)

        combos_payload: list[dict[str, Any]] = []
        for combo in detection.combos:
            payload = combo.to_payload()
            combo_id = payload.get("combo_id")
            if isinstance(combo_id, str):
                payload.setdefault("id", combo_id)
            extras = grouping.combo_extras.get(combo.combo_id)
            if isinstance(extras, dict):
                payload.update(extras)
                group_id = extras.get("combo_group_id")
                if isinstance(group_id, str):
                    group_payload = group_lookup.get(group_id)
                    if isinstance(group_payload, dict):
                        payload.setdefault("group_qty", group_payload.get("group_qty"))
                        payload.setdefault("group_net_price", group_payload.get("group_net_price"))
                        payload.setdefault("group_mark_source", group_payload.get("mark_source"))
                        payload.setdefault("group_stale_seconds", group_payload.get("stale_seconds"))
                        display_payload = group_payload.get("display")
                        if display_payload and "display" not in payload:
                            payload["display"] = deepcopy(display_payload)
            playbook_fields = evaluation.combo_targets.get(combo.combo_id)
            if isinstance(playbook_fields, dict):
                payload.update(playbook_fields)
            for leg_payload in payload.get("legs", []):
                leg_id = leg_payload.get("leg_id")
                if isinstance(leg_id, str):
                    leg_payload.setdefault("id", leg_id)
                    leg_extra = grouping.leg_extras.get(leg_id)
                    if isinstance(leg_extra, dict):
                        leg_payload.update(leg_extra)
                        group_id = leg_extra.get("combo_group_id")
                        if isinstance(group_id, str):
                            group_payload = group_lookup.get(group_id)
                            if isinstance(group_payload, dict):
                                leg_payload.setdefault("group_qty", group_payload.get("group_qty"))
                                leg_payload.setdefault("group_net_price", group_payload.get("group_net_price"))
                                leg_payload.setdefault("group_mark_source", group_payload.get("mark_source"))
                                leg_payload.setdefault("group_stale_seconds", group_payload.get("stale_seconds"))
                    leg_fields = evaluation.leg_targets.get(leg_id)
                    if isinstance(leg_fields, dict):
                        leg_payload.update(leg_fields)
            combos_payload.append(payload)

        legs_payload: list[dict[str, Any]] = []
        for leg in detection.orphans:
            payload = leg.to_payload()
            leg_id = payload.get("leg_id")
            if isinstance(leg_id, str):
                payload.setdefault("id", leg_id)
            leg_extra = grouping.leg_extras.get(leg.leg_id)
            if isinstance(leg_extra, dict):
                payload.update(leg_extra)
                group_id = leg_extra.get("combo_group_id")
                if isinstance(group_id, str):
                    group_payload = group_lookup.get(group_id)
                    if isinstance(group_payload, dict):
                        payload.setdefault("group_qty", group_payload.get("group_qty"))
                        payload.setdefault("group_net_price", group_payload.get("group_net_price"))
                        payload.setdefault("group_mark_source", group_payload.get("mark_source"))
                        payload.setdefault("group_stale_seconds", group_payload.get("stale_seconds"))
            else:
                display = build_leg_display(leg.underlying, leg.strike, leg.right, leg.expiry)
                payload["label"] = display.leg_label
                payload["display"] = {
                    "leg_label": display.leg_label,
                    "short_ul": display.short_ul,
                    "expiry_short": display.expiry_short,
                }
            leg_fields = evaluation.leg_targets.get(leg.leg_id)
            if isinstance(leg_fields, dict):
                payload.update(leg_fields)
            legs_payload.append(payload)

        result = {
            "as_of": _isoformat(as_of),
            "combos": combos_payload,
            "combo_groups": combo_groups_payload,
            "legs": legs_payload,
        }
        if evaluation.meta:
            result["playbook"] = evaluation.meta
        return result

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

        now = _ensure_aware(now)
        if self._positions_view_raw is not None:
            sanitized_upstream = _sanitize_positions_view(self._positions_view_raw)
            payload, sanitized_view = self._augment_upstream_view_if_needed(
                self._positions_view_raw,
                sanitized_upstream,
                now,
            )
            self._positions_view = sanitized_view
            if _positions_view_has_rows(sanitized_view):
                return payload
            fallback_view = self.build_fallback_positions_view(now)
            if _positions_view_has_rows(fallback_view):
                self._log_upstream_empty_once()
                self._positions_view = fallback_view
                return deepcopy(fallback_view)
            return payload
        if self._positions_view is not None and _positions_view_has_rows(self._positions_view):
            return deepcopy(self._positions_view)
        fallback_view = self.build_fallback_positions_view(now)
        self._positions_view = fallback_view
        return deepcopy(fallback_view)

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

    def build_fallback_positions_view(self, now: datetime | None = None) -> dict[str, Any]:
        """Construct a synthesized positions_view from the current state."""

        view = self._build_positions_view(now)
        return _sanitize_positions_view(view)

    def _build_positions_view(self, now: datetime | None) -> dict[str, Any]:
        now = _ensure_aware(now)
        equities_view = [_equity_view_from_row(row) for row in self.equities_payload(now)]
        detection, _ = self._ensure_options_detection(now)
        grouping = group_option_combos(detection.combos)
        combo_groups_payload = [group.to_payload() for group in grouping.groups]
        group_lookup = {
            payload["combo_group_id"]: payload
            for payload in combo_groups_payload
            if isinstance(payload, dict) and isinstance(payload.get("combo_group_id"), str)
        }

        evaluation = evaluate_playbook_targets(detection.combos, detection.orphans, self._quotes)

        combos_view: list[dict[str, Any]] = []
        for combo in detection.combos:
            combo_payload = _combo_view_from_detection(combo)
            extras = grouping.combo_extras.get(combo.combo_id)
            if isinstance(extras, dict):
                combo_payload.update(extras)
                group_id = extras.get("combo_group_id")
                if isinstance(group_id, str):
                    group_payload = group_lookup.get(group_id)
                    if isinstance(group_payload, dict):
                        combo_payload.setdefault("group_qty", group_payload.get("group_qty"))
                        combo_payload.setdefault("group_net_price", group_payload.get("group_net_price"))
                        combo_payload.setdefault("group_mark_source", group_payload.get("mark_source"))
                        combo_payload.setdefault("group_stale_seconds", group_payload.get("stale_seconds"))
                        display_payload = group_payload.get("display")
                        if display_payload and "display" not in combo_payload:
                            combo_payload["display"] = deepcopy(display_payload)
            playbook_fields = evaluation.combo_targets.get(combo.combo_id)
            if isinstance(playbook_fields, dict):
                combo_payload.update(playbook_fields)
            for leg_payload in combo_payload.get("legs", []):
                leg_id = leg_payload.get("leg_id")
                if isinstance(leg_id, str):
                    leg_fields = evaluation.leg_targets.get(leg_id)
                    if isinstance(leg_fields, dict):
                        leg_payload.update(leg_fields)
            combos_view.append(combo_payload)

        single_options_view: list[dict[str, Any]] = []
        for leg in detection.orphans:
            leg_payload = _option_leg_view_from_detection(leg)
            leg_extras = grouping.leg_extras.get(leg.leg_id)
            if isinstance(leg_extras, dict):
                leg_payload.update(leg_extras)
                group_id = leg_extras.get("combo_group_id")
                if isinstance(group_id, str):
                    group_payload = group_lookup.get(group_id)
                    if isinstance(group_payload, dict):
                        leg_payload.setdefault("group_qty", group_payload.get("group_qty"))
                        leg_payload.setdefault("group_net_price", group_payload.get("group_net_price"))
                        leg_payload.setdefault("group_mark_source", group_payload.get("mark_source"))
                        leg_payload.setdefault("group_stale_seconds", group_payload.get("stale_seconds"))
            leg_fields = evaluation.leg_targets.get(leg.leg_id)
            if isinstance(leg_fields, dict):
                leg_payload.update(leg_fields)
            single_options_view.append(leg_payload)

        view: dict[str, Any] = {
            "single_stocks": equities_view,
            "option_combos": combos_view,
            "single_options": single_options_view,
        }
        if combo_groups_payload:
            view["combo_groups"] = combo_groups_payload
        if evaluation.meta:
            view["playbook"] = evaluation.meta
        return view

    def _log_upstream_empty_once(self) -> None:
        if not self._upstream_view_fallback_logged:
            logger.info("[state] upstream view empty; using synthesized view")
            self._upstream_view_fallback_logged = True

    def _log_upstream_missing_combos_once(self, combos_count: int) -> None:
        if not self._upstream_view_missing_combos_logged:
            logger.info(
                "[state] upstream view had legs but no combos; grouped %d combos",
                combos_count,
            )
            self._upstream_view_missing_combos_logged = True

    def _resolve_session(self) -> str:
        for quote in self._quotes.values():
            session = quote.session
            if isinstance(session, TradingSession):
                return session.value
            if isinstance(session, str) and session:
                return session
        return TradingSession.CLOSED.value

    def _augment_upstream_view_if_needed(
        self,
        raw_view: dict[str, Any],
        sanitized_view: dict[str, Any],
        now: datetime,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        option_combos = sanitized_view.get("option_combos")
        single_options = sanitized_view.get("single_options")
        if (
            isinstance(single_options, list)
            and single_options
            and isinstance(option_combos, list)
            and len(option_combos) == 0
        ):
            fallback_view = self.build_fallback_positions_view(now)
            fallback_combos = fallback_view.get("option_combos") or []
            fallback_groups = fallback_view.get("combo_groups") or []
            if fallback_combos:
                augmented_sanitized = deepcopy(sanitized_view)
                augmented_sanitized["option_combos"] = deepcopy(fallback_combos)
                if fallback_groups:
                    augmented_sanitized["combo_groups"] = deepcopy(fallback_groups)
                elif "combo_groups" in augmented_sanitized:
                    augmented_sanitized["combo_groups"] = []

                augmented_payload = deepcopy(raw_view)
                augmented_payload["option_combos"] = deepcopy(fallback_combos)
                if fallback_groups:
                    augmented_payload["combo_groups"] = deepcopy(fallback_groups)
                elif "combo_groups" in augmented_payload:
                    augmented_payload["combo_groups"] = []

                self._log_upstream_missing_combos_once(len(fallback_combos))
                return augmented_payload, augmented_sanitized
        return deepcopy(raw_view), sanitized_view

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


def _positions_view_has_rows(view: dict[str, Any] | None) -> bool:
    if not isinstance(view, dict):
        return False
    for key in ("single_stocks", "option_combos", "single_options"):
        entries = view.get(key)
        if isinstance(entries, list) and len(entries) > 0:
            return True
    return False


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
    day_pnl = _to_float(row.get("day_pnl"))
    day_pnl_percent = _to_float(row.get("day_pnl_percent"))
    total_pnl = _to_float(row.get("total_pnl"))
    total_pnl_percent = _to_float(row.get("total_pnl_percent"))
    stale_seconds = _to_int(row.get("stale_seconds"))
    mark_source = row.get("mark_source")
    price_source = _safe_lower(mark_source) or mark_source
    return {
        "secType": "STK",
        "symbol": symbol,
        "qty": qty if qty is not None else 0.0,
        "avg_cost": avg_cost,
        "multiplier": 1,
        "mark": mark,
        "mark_source": mark_source,
        "price_source": price_source,
        "stale_s": stale_seconds,
        "stale_seconds": stale_seconds,
        "day_pnl": day_pnl,
        "day_pnl_percent": day_pnl_percent,
        "pnl_intraday": day_pnl,
        "pnl_unrealized": total_pnl,
        "total_pnl": total_pnl,
        "total_pnl_percent": total_pnl_percent,
        "greeks": {"delta": None, "gamma": None, "theta": None},
        "previous_close": _to_float(row.get("previous_close")),
    }


def _combo_view_from_detection(combo: OptionCombo) -> dict[str, Any]:
    legs = [_option_leg_view_from_detection(leg) for leg in combo.legs]
    day_pnl = _to_float(combo.day_pnl)
    total_pnl = _to_float(combo.total_pnl)
    return {
        "combo_id": combo.combo_id,
        "name": strategy_label(combo.strategy),
        "strategy": combo.strategy.value,
        "underlier": combo.underlying,
        "account": combo.account,
        "dte": combo.dte,
        "net_price": _to_float(combo.net_price),
        "pnl_intraday": day_pnl,
        "pnl_unrealized": total_pnl,
        "day_pnl": day_pnl,
        "total_pnl": total_pnl,
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
    day_pnl = _to_float(leg.day_pnl)
    total_pnl = _to_float(leg.total_pnl)
    stale_seconds = leg.stale_seconds
    mark_source = leg.mark_source
    price_source = _safe_lower(mark_source) or mark_source
    return {
        "secType": "OPT",
        "symbol": leg.instrument_symbol,
        "underlying": leg.underlying,
        "qty": qty if qty is not None else 0.0,
        "avg_cost": avg_cost,
        "multiplier": _to_float(leg.multiplier),
        "mark": mark,
        "mark_source": mark_source,
        "price_source": price_source,
        "stale_s": stale_seconds,
        "stale_seconds": stale_seconds,
        "pnl_intraday": day_pnl,
        "pnl_unrealized": total_pnl,
        "day_pnl": day_pnl,
        "total_pnl": total_pnl,
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
