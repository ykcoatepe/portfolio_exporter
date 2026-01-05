# SPDX-License-Identifier: MIT

"""In-memory joiner for normalized position snapshots."""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Iterable
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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
from ..core.session import detect_session
from ..ingest.internal import InternalScriptsProvider
from .normalize import (
    compute_equity_pnl_fields,
    positions_from_records,
    quotes_from_records,
)

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
        self._latest_ts: datetime | None = None
        self._live_seen: dict[str, int] = {"quotes": 0, "greeks": 0}
        self._greeks_refresh_supported = True

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

    def refresh_live_snapshot(self) -> None:
        """Refresh quotes/greeks from the internal provider without altering API availability."""

        provider = InternalScriptsProvider()
        try:
            positions_records, quotes_records = provider.load()
        except Exception:  # pragma: no cover - defensive
            logger.info("[refresh] internal provider load failed", exc_info=True)
            return

        fresh_positions = (
            positions_from_records(positions_records) if positions_records else []
        )
        fresh_quotes = quotes_from_records(quotes_records) if quotes_records else []

        positions_changed = False
        quotes_changed = False
        greeks_seen = 0
        quotes_seen = len(fresh_quotes)

        fresh_map = {
            position.instrument.symbol: position for position in fresh_positions
        }
        greeks_seen = sum(
            1
            for position in fresh_map.values()
            if any(
                position.metadata.get(key) is not None
                for key in ("delta", "gamma", "theta", "vega")
            )
        )
        if not fresh_map:
            if self._positions:
                self._positions = {}
                positions_changed = True
        else:
            updated_positions: dict[str, Position] = {}
            for symbol, existing in self._positions.items():
                replacement = fresh_map.get(symbol)
                if replacement is None:
                    updated_positions[symbol] = existing
                    continue
                update_fields: dict[str, Any] = {}
                if replacement.quantity != existing.quantity:
                    update_fields["quantity"] = replacement.quantity
                if (
                    replacement.avg_cost is not None
                    and replacement.avg_cost != existing.avg_cost
                ):
                    update_fields["avg_cost"] = replacement.avg_cost
                if replacement.cost_basis != existing.cost_basis:
                    update_fields["cost_basis"] = replacement.cost_basis
                if replacement.metadata != existing.metadata:
                    update_fields["metadata"] = replacement.metadata
                if update_fields:
                    updated_positions[symbol] = existing.model_copy(
                        update=update_fields
                    )
                    positions_changed = True
                else:
                    updated_positions[symbol] = existing
            for symbol, replacement in fresh_map.items():
                if symbol not in updated_positions:
                    updated_positions[symbol] = replacement
                    positions_changed = True
            if positions_changed:
                self._positions = updated_positions

        if fresh_quotes:
            merged_quotes = dict(self._quotes)
            for quote in fresh_quotes:
                current = merged_quotes.get(quote.symbol)
                if current != quote:
                    merged_quotes[quote.symbol] = quote
                    quotes_changed = True
            if quotes_changed:
                self._quotes = merged_quotes

        if positions_changed or quotes_changed:
            self._options_cache = None
        if positions_changed:
            self._positions_version += 1
            self._positions_view = None
            self._positions_view_raw = None
        if quotes_changed:
            self._quotes_version += 1
            self._snapshot_override = None

        session_as_of = _parse_iso_datetime_safe(detect_session().as_of)
        quote_latest = _latest_quote_timestamp(self._quotes.values())
        self._latest_ts = _max_datetime([self._latest_ts, quote_latest, session_as_of])
        self._live_seen["quotes"] = quotes_seen
        self._live_seen["greeks"] = greeks_seen

    def refresh_live_greeks(self) -> None:
        """Refresh option greeks metadata without replacing quotes."""

        provider = InternalScriptsProvider()
        try:
            snapshot = provider.load_greeks_snapshot()
        except Exception:  # pragma: no cover - defensive
            logger.info("[refresh] greeks snapshot load failed", exc_info=True)
            self._greeks_refresh_supported = False
            return

        if not snapshot:
            if self._greeks_refresh_supported:
                logger.debug(
                    "[refresh] greeks snapshot unavailable from internal provider"
                )
                self._greeks_refresh_supported = False
            return

        self._greeks_refresh_supported = True
        greeks_map, snapshot_ts = _extract_greeks_map(snapshot)
        if not greeks_map:
            return

        positions_updated = False
        updated_positions: dict[str, Position] = {}
        for symbol, position in self._positions.items():
            greeks = greeks_map.get(symbol)
            if not greeks:
                updated_positions[symbol] = position
                continue
            metadata = dict(position.metadata)
            changed = False
            for key, value in greeks.items():
                if metadata.get(key) != value:
                    metadata[key] = value
                    changed = True
            if changed:
                updated_positions[symbol] = position.model_copy(
                    update={"metadata": metadata}
                )
                positions_updated = True
            else:
                updated_positions[symbol] = position

        if positions_updated:
            self._positions = updated_positions
            self._positions_version += 1
            self._options_cache = None
            self._positions_view = None
            self._positions_view_raw = None

        if snapshot_ts is not None:
            self._latest_ts = _max_datetime([self._latest_ts, snapshot_ts])
        self._live_seen["greeks"] = len(greeks_map)

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
        for group_payload in combo_groups_payload:
            if isinstance(group_payload, dict):
                _apply_combo_mark_metadata(group_payload)
                legs = group_payload.get("legs")
                if isinstance(legs, list):
                    for leg_payload in legs:
                        if isinstance(leg_payload, dict):
                            _normalize_option_mark_payload(leg_payload, now=as_of)
        group_lookup = {
            payload["combo_group_id"]: payload
            for payload in combo_groups_payload
            if isinstance(payload, dict)
            and isinstance(payload.get("combo_group_id"), str)
        }

        evaluation = evaluate_playbook_targets(
            detection.combos, detection.orphans, self._quotes
        )

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
                        payload.setdefault(
                            "group_net_price", group_payload.get("group_net_price")
                        )
                        payload.setdefault(
                            "group_mark_source", group_payload.get("mark_source")
                        )
                        payload.setdefault(
                            "group_stale_seconds", group_payload.get("stale_seconds")
                        )
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
                                leg_payload.setdefault(
                                    "group_qty", group_payload.get("group_qty")
                                )
                                leg_payload.setdefault(
                                    "group_net_price",
                                    group_payload.get("group_net_price"),
                                )
                                leg_payload.setdefault(
                                    "group_mark_source",
                                    group_payload.get("mark_source"),
                                )
                                leg_payload.setdefault(
                                    "group_stale_seconds",
                                    group_payload.get("stale_seconds"),
                                )
                    leg_fields = evaluation.leg_targets.get(leg_id)
                    if isinstance(leg_fields, dict):
                        leg_payload.update(leg_fields)
                _normalize_option_mark_payload(leg_payload, now=as_of)
            _apply_combo_mark_metadata(payload)
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
                        payload.setdefault(
                            "group_net_price", group_payload.get("group_net_price")
                        )
                        payload.setdefault(
                            "group_mark_source", group_payload.get("mark_source")
                        )
                        payload.setdefault(
                            "group_stale_seconds", group_payload.get("stale_seconds")
                        )
            else:
                display = build_leg_display(
                    leg.underlying, leg.strike, leg.right, leg.expiry
                )
                payload["label"] = display.leg_label
                payload["display"] = {
                    "leg_label": display.leg_label,
                    "short_ul": display.short_ul,
                    "expiry_short": display.expiry_short,
                }
            leg_fields = evaluation.leg_targets.get(leg.leg_id)
            if isinstance(leg_fields, dict):
                payload.update(leg_fields)
            _normalize_option_mark_payload(payload, now=as_of)
            legs_payload.append(payload)

        _merge_playbook_into_combo_groups(combo_groups_payload, combos_payload)

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

    def stats(self, now: datetime | None = None) -> dict[str, Any]:
        rows, stale = self._rows(now)
        detection, _ = self._ensure_options_detection(now)
        legs_count = sum(len(combo.legs) for combo in detection.combos) + len(
            detection.orphans
        )
        payload: dict[str, Any] = {
            "equity_count": len(rows),
            "quote_count": len(self._quotes),
            "stale_quotes_count": stale,
            "option_legs_count": legs_count,
            "combos_matched": len(detection.combos),
            "combos_detection_ms": detection.detection_ms,
            "data_source": self._data_source,
        }
        meta: dict[str, Any] = {}
        if self._latest_ts is not None:
            meta["latest_ts"] = _isoformat(self._latest_ts)
        if self._live_seen:
            meta["live_seen"] = dict(self._live_seen)
        if meta:
            payload["meta"] = meta
        return payload

    @property
    def data_source(self) -> str:
        return self._data_source

    def quotes_snapshot(self) -> dict[str, Quote]:
        """Return a shallow copy of the latest quotes keyed by symbol."""

        return dict(self._quotes)

    def positions_view_payload(self, now: datetime | None = None) -> dict[str, Any]:
        """Return the most recent positions_view, computing a fallback if needed."""

        now = _ensure_aware(now)
        if self._positions_view_raw is not None:
            sanitized_upstream = _sanitize_positions_view(self._positions_view_raw)
            _normalize_mark_payload(sanitized_upstream, now)
            payload, sanitized_view = self._augment_upstream_view_if_needed(
                self._positions_view_raw,
                sanitized_upstream,
                now,
            )
            _normalize_mark_payload(payload, now)
            _normalize_mark_payload(sanitized_view, now)
            self._positions_view = sanitized_view
            if _positions_view_has_rows(sanitized_view):
                return payload
            fallback_view = self.build_fallback_positions_view(now)
            if _positions_view_has_rows(fallback_view):
                self._log_upstream_empty_once()
                self._positions_view = fallback_view
                return deepcopy(fallback_view)
            return payload
        if self._positions_view is not None and _positions_view_has_rows(
            self._positions_view
        ):
            payload = deepcopy(self._positions_view)
            _normalize_mark_payload(payload, now)
            return payload
        fallback_view = self.build_fallback_positions_view(now)
        self._positions_view = fallback_view
        return deepcopy(fallback_view)

    def snapshot_payload(self, now: datetime | None = None) -> dict[str, Any]:
        """Return a PSD-style snapshot for /state consumers."""

        now = _ensure_aware(now)
        snapshot_at = self.snapshot_updated_at()
        ts = int(snapshot_at.timestamp() * 1000) if snapshot_at is not None else None
        positions_view = self.positions_view_payload(now)
        positions_dump = [
            position.model_dump(mode="json") for position in self._positions.values()
        ]
        quotes_dump = {
            symbol: quote.model_dump(mode="json")
            for symbol, quote in self._quotes.items()
        }
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
            pnl_fields = compute_equity_pnl_fields(
                position=position,
                mark=mark.mark,
                previous_close=prev_close,
            )
            row = {
                "symbol": symbol,
                "qty": float(position.quantity),
                "avg_cost": float(position.avg_cost)
                if position.avg_cost is not None
                else None,
                "mark": float(mark_value),
                "mark_source": mark.source,
                "previous_close": float(prev_close) if prev_close is not None else None,
                "stale_seconds": mark.stale_seconds,
            }
            row.update(pnl_fields)
            rows.append(row)
        return rows, stale

    def build_fallback_positions_view(
        self, now: datetime | None = None
    ) -> dict[str, Any]:
        """Construct a synthesized positions_view from the current state."""

        view = self._build_positions_view(now)
        sanitized = _sanitize_positions_view(view)
        _normalize_mark_payload(sanitized, now)
        return sanitized

    def _build_positions_view(self, now: datetime | None) -> dict[str, Any]:
        now = _ensure_aware(now)
        equities_view = [
            _equity_view_from_row(row) for row in self.equities_payload(now)
        ]
        detection, _ = self._ensure_options_detection(now)
        grouping = group_option_combos(detection.combos)
        combo_groups_payload = [group.to_payload() for group in grouping.groups]
        group_lookup = {
            payload["combo_group_id"]: payload
            for payload in combo_groups_payload
            if isinstance(payload, dict)
            and isinstance(payload.get("combo_group_id"), str)
        }

        evaluation = evaluate_playbook_targets(
            detection.combos, detection.orphans, self._quotes
        )

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
                        combo_payload.setdefault(
                            "group_qty", group_payload.get("group_qty")
                        )
                        combo_payload.setdefault(
                            "group_net_price", group_payload.get("group_net_price")
                        )
                        combo_payload.setdefault(
                            "group_mark_source", group_payload.get("mark_source")
                        )
                        combo_payload.setdefault(
                            "group_stale_seconds", group_payload.get("stale_seconds")
                        )
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

        _merge_playbook_into_combo_groups(combo_groups_payload, combos_view)

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
                        leg_payload.setdefault(
                            "group_qty", group_payload.get("group_qty")
                        )
                        leg_payload.setdefault(
                            "group_net_price", group_payload.get("group_net_price")
                        )
                        leg_payload.setdefault(
                            "group_mark_source", group_payload.get("mark_source")
                        )
                        leg_payload.setdefault(
                            "group_stale_seconds", group_payload.get("stale_seconds")
                        )
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

    def _ensure_options_detection(
        self, now: datetime | None
    ) -> tuple[ComboDetection, datetime]:
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


def _latest_quote_timestamp(quotes: Iterable[Quote]) -> datetime | None:
    latest: datetime | None = None
    for quote in quotes:
        for candidate in (
            quote.updated_at,
            quote.bid_ts,
            quote.ask_ts,
            quote.last_ts,
            quote.previous_close_ts,
        ):
            if candidate is None:
                continue
            aware = _ensure_aware(candidate)
            if latest is None or aware > latest:
                latest = aware
    return latest


def _parse_iso_datetime_safe(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _ensure_aware(parsed)


def _max_datetime(values: Iterable[datetime | None]) -> datetime | None:
    latest: datetime | None = None
    for value in values:
        if value is None:
            continue
        candidate = _ensure_aware(value)
        if latest is None or candidate > latest:
            latest = candidate
    return latest


def _extract_greeks_map(
    payload: Any,
) -> tuple[dict[str, dict[str, Decimal]], datetime | None]:
    rows: list[dict[str, Any]] = []
    timestamp: datetime | None = None

    def _collect(candidate: Any) -> None:
        if isinstance(candidate, list):
            rows.extend(entry for entry in candidate if isinstance(entry, dict))

    if isinstance(payload, dict):
        for key in ("rows", "legs", "options", "positions", "data"):
            _collect(payload.get(key))
        if not rows:
            _collect(payload.get("greeks"))
        timestamp = _parse_maybe_timestamp(
            payload.get("as_of")
            or payload.get("timestamp")
            or payload.get("ts")
            or payload.get("updated_at")
        )
    elif isinstance(payload, list):
        _collect(payload)
    else:
        return {}, None

    greeks_map: dict[str, dict[str, Decimal]] = {}
    for entry in rows:
        symbol = (
            entry.get("symbol")
            or entry.get("instrument_symbol")
            or entry.get("leg_symbol")
        )
        if not isinstance(symbol, str) or not symbol.strip():
            continue
        clean_symbol = symbol.strip()
        greeks_values: dict[str, Decimal] = {}
        for greek_key in ("delta", "gamma", "theta", "vega"):
            value = entry.get(greek_key)
            decimal_value = _coerce_decimal(value)
            if decimal_value is not None:
                greeks_values[greek_key] = decimal_value
        if greeks_values:
            greeks_map[clean_symbol] = greeks_values

    return greeks_map, timestamp


def _parse_maybe_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, (int, float)):
        seconds = float(value)
        if not math.isfinite(seconds):
            return None
        if seconds > 1e12:
            seconds /= 1000.0
        return datetime.fromtimestamp(seconds, tz=UTC)
    if isinstance(value, str):
        parsed = _parse_iso_datetime_safe(value)
        if parsed is not None:
            return parsed
    return None


def _coerce_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


class _GroupPlaybookAccumulator:
    """Aggregate combo playbook metrics for a combo group."""

    __slots__ = (
        "tp_band_low_pct",
        "tp_band_high_pct",
        "tp_hit",
        "tp_done",
        "sl_hit",
        "sl_r",
        "next_action",
        "exit_as_unit",
        "progress_goal_sum",
        "progress_goal_count",
        "progress_max_sum",
        "progress_max_count",
    )

    def __init__(self) -> None:
        self.tp_band_low_pct: float | None = None
        self.tp_band_high_pct: float | None = None
        self.tp_hit = False
        self.tp_done = False
        self.sl_hit = False
        self.sl_r: float | None = None
        self.next_action: str | None = None
        self.exit_as_unit = False
        self.progress_goal_sum = 0.0
        self.progress_goal_count = 0
        self.progress_max_sum = 0.0
        self.progress_max_count = 0

    def consume(self, combo: dict[str, Any]) -> None:
        band_low = _coerce_float(combo.get("tp_band_low_pct"))
        band_high = _coerce_float(combo.get("tp_band_high_pct"))
        band = combo.get("tp_band_pct")
        if isinstance(band, (list, tuple)):
            if band_low is None and len(band) >= 1:
                band_low = _coerce_float(band[0])
            if band_high is None and len(band) >= 2:
                band_high = _coerce_float(band[1])
        if band_low is not None and self.tp_band_low_pct is None:
            self.tp_band_low_pct = band_low
        if band_high is not None and self.tp_band_high_pct is None:
            self.tp_band_high_pct = band_high

        if combo.get("tp_hit"):
            self.tp_hit = True
        if combo.get("tp_done"):
            self.tp_done = True
        if combo.get("sl_hit"):
            self.sl_hit = True

        sl_r_value = _coerce_float(combo.get("sl_r"))
        if self.sl_r is None and sl_r_value is not None:
            self.sl_r = sl_r_value

        next_action_value = combo.get("next_action")
        if isinstance(next_action_value, str):
            action = next_action_value.strip().upper()
            if action:
                current = self.next_action
                if current and current != "HOLD":
                    pass
                elif action == "HOLD":
                    if current is None:
                        self.next_action = "HOLD"
                else:
                    self.next_action = action

        if combo.get("exit_as_unit"):
            self.exit_as_unit = True

        progress_value = combo.get("progress")
        progress_dict = progress_value if isinstance(progress_value, dict) else None
        goal_value: Any = combo.get("progress_pct_of_goal")
        if goal_value is None and progress_dict is not None:
            goal_value = progress_dict.get("pct_of_goal")
        goal_float = _coerce_float(goal_value)
        if goal_float is not None:
            self.progress_goal_sum += goal_float
            self.progress_goal_count += 1

        max_value: Any = combo.get("progress_pct_of_max")
        if max_value is None and progress_dict is not None:
            max_value = progress_dict.get("pct_of_max_profit_or_r")
        max_float = _coerce_float(max_value)
        if max_float is not None:
            self.progress_max_sum += max_float
            self.progress_max_count += 1

    def apply(self, target: dict[str, Any]) -> None:
        band_low = self.tp_band_low_pct
        band_high = self.tp_band_high_pct
        target["tp_band_low_pct"] = band_low
        target["tp_band_high_pct"] = band_high
        target["tp_band_pct"] = (
            [band_low, band_high]
            if band_low is not None and band_high is not None
            else None
        )
        target["tp_hit"] = self.tp_hit
        target["tp_done"] = self.tp_done
        target["sl_hit"] = self.sl_hit
        target["sl_r"] = self.sl_r
        target["exit_as_unit"] = self.exit_as_unit
        action = self.next_action
        if action == "HOLD":
            action = None
        target["next_action"] = action
        goal_avg = self._average(self.progress_goal_sum, self.progress_goal_count)
        max_avg = self._average(self.progress_max_sum, self.progress_max_count)
        target["progress_pct_of_goal"] = goal_avg
        target["progress_pct_of_max"] = max_avg
        target["progress"] = {
            "pct_of_goal": goal_avg,
            "pct_of_max_profit_or_r": max_avg,
        }

    @staticmethod
    def _average(total: float, count: int) -> float | None:
        if count <= 0:
            return None
        value = total / count
        if not math.isfinite(value):
            return None
        return value


def _merge_playbook_into_combo_groups(
    combo_groups: list[dict[str, Any]],
    combos: Iterable[dict[str, Any]],
) -> None:
    if not combo_groups:
        return
    group_lookup = {
        group.get("combo_group_id"): group
        for group in combo_groups
        if isinstance(group, dict) and isinstance(group.get("combo_group_id"), str)
    }
    if not group_lookup:
        return
    accumulators: dict[str, _GroupPlaybookAccumulator] = {}
    for combo in combos:
        if not isinstance(combo, dict):
            continue
        group_id = combo.get("combo_group_id")
        if not isinstance(group_id, str):
            continue
        if group_id not in group_lookup:
            continue
        accumulator = accumulators.setdefault(group_id, _GroupPlaybookAccumulator())
        accumulator.consume(combo)
    for group_id, accumulator in accumulators.items():
        group_payload = group_lookup.get(group_id)
        if group_payload is None:
            continue
        accumulator.apply(group_payload)


def _sanitize_positions_view(view: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key in ("single_stocks", "option_combos", "single_options"):
        sanitized[key] = []
        raw = view.get(key)
        if isinstance(raw, list):
            if key == "option_combos":
                sanitized[key] = [
                    _sanitize_combo_entry(entry)
                    for entry in raw
                    if isinstance(entry, dict)
                ]
            else:
                sanitized[key] = [
                    deepcopy(entry) for entry in raw if isinstance(entry, dict)
                ]
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

    def _first_float(*keys: str) -> float | None:
        for key in keys:
            candidate = _to_float(row.get(key))
            if candidate is not None:
                return candidate
        return None

    day_pnl = _first_float("day_pnl", "pnl_intraday")
    day_pnl_percent = _first_float("day_pnl_percent", "day_pnl_pct")
    total_pnl = _first_float("total_pnl", "pnl_unrealized")
    total_pnl_percent = _first_float(
        "total_pnl_percent", "pnl_unrealized_percent", "pnl_unrealized_pct"
    )
    pnl_unrealized = _first_float("pnl_unrealized", "total_pnl")
    pnl_unrealized_percent = _first_float(
        "pnl_unrealized_percent", "pnl_unrealized_pct", "total_pnl_percent"
    )
    stale_seconds = _to_int(row.get("stale_seconds"))
    mark_source = _canonical_mark_source(row.get("mark_source"))
    price_source = _safe_lower(mark_source) if mark_source is not None else None
    if price_source is None:
        raw_source = row.get("mark_source")
        price_source = _safe_lower(raw_source) or raw_source
    if total_pnl is None:
        total_pnl = pnl_unrealized
    if pnl_unrealized is None:
        pnl_unrealized = total_pnl
    if total_pnl_percent is None:
        total_pnl_percent = pnl_unrealized_percent
    if pnl_unrealized_percent is None:
        pnl_unrealized_percent = total_pnl_percent
    pnl_unrealized_pct = _first_float(
        "pnl_unrealized_pct", "pnl_unrealized_percent", "total_pnl_percent"
    )
    day_pnl_pct = _first_float("day_pnl_pct", "day_pnl_percent")
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
        "day_pnl_pct": day_pnl_pct,
        "pnl_intraday": day_pnl,
        "pnl_unrealized": pnl_unrealized,
        "pnl_unrealized_percent": pnl_unrealized_percent,
        "pnl_unrealized_pct": pnl_unrealized_pct,
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
    mark_source = _canonical_mark_source(leg.mark_source)
    price_source = _safe_lower(mark_source) if mark_source is not None else None
    if price_source is None:
        price_source = _safe_lower(leg.mark_source) or leg.mark_source
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


_PREV_STALE_FALLBACK_SECONDS = 24 * 60 * 60  # legacy export for compatibility
_MARK_SOURCE_ALIASES = {"LAST_CLOSE": "PREV"}
_MARK_SOURCE_PRIORITY = {"MID": 0, "LAST": 1, "PREV": 2}


def _normalize_option_mark_payload(
    entry: dict[str, Any], *, now: datetime
) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return entry
    now = _ensure_aware(now)
    _ensure_canonical_timestamp(entry, "bid_ts", _OPTION_BID_TS_ALIASES)
    _ensure_canonical_timestamp(entry, "ask_ts", _OPTION_ASK_TS_ALIASES)
    _ensure_canonical_timestamp(entry, "last_ts", _OPTION_LAST_TS_ALIASES)
    _ensure_canonical_timestamp(
        entry, "previous_close_ts", _OPTION_PREVIOUS_CLOSE_TS_ALIASES
    )
    raw_source = entry.get("mark_source")
    if not raw_source:
        raw_source = entry.get("source")
    alias_from_last_close = (
        isinstance(raw_source, str) and raw_source.strip().upper() == "LAST_CLOSE"
    )
    mark_source = _canonical_mark_source(raw_source)
    if mark_source is not None:
        entry["mark_source"] = mark_source
        entry["price_source"] = _safe_lower(mark_source) or mark_source
        if alias_from_last_close and mark_source == "PREV":
            # Preserve a real timestamp for PREV so staleness is accurate.
            prev_ts = (
                entry.get("last_close_ts") or entry.get("ts") or entry.get("last_ts")
            )
            if prev_ts is not None:
                entry["prev_ts"] = prev_ts
    elif "mark_source" in entry:
        entry["mark_source"] = None
    if mark_source == "PREV" and entry.get("previous_close_ts") in (None, "", 0):
        fallback_ts = _extract_timestamp_from_entry(
            entry, _OPTION_PREVIOUS_CLOSE_TS_ALIASES
        )
        if fallback_ts is None and alias_from_last_close:
            fallback_ts = _extract_timestamp_from_entry(
                entry, _OPTION_LAST_TIMESTAMP_KEYS
            )
        if fallback_ts is None:
            fallback_ts = _extract_timestamp_from_entry(
                entry, _OPTION_UPDATED_TIMESTAMP_KEYS
            )
        if fallback_ts is not None:
            iso = _isoformat(fallback_ts)
            entry["previous_close_ts"] = iso
            entry.setdefault("prev_ts", iso)
    if mark_source == "PREV" and entry.get("prev_ts") in (None, ""):
        prev_timestamp = _extract_timestamp_from_entry(
            entry, _OPTION_PREVIOUS_CLOSE_TS_ALIASES
        )
        if prev_timestamp is not None:
            entry["prev_ts"] = _isoformat(prev_timestamp)
    stale_seconds = _resolve_option_stale_seconds_entry(entry, mark_source, now)
    if stale_seconds is not None:
        entry["stale_seconds"] = stale_seconds
        entry["stale_s"] = stale_seconds
    return entry


def _apply_combo_mark_metadata(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        return
    legs = payload.get("legs") if isinstance(payload.get("legs"), list) else None
    sources: list[str | None] = []
    stale_candidates: list[int] = []
    if legs is not None:
        for leg in legs:
            if not isinstance(leg, dict):
                continue
            sources.append(leg.get("mark_source"))
            candidate = _to_int(leg.get("stale_seconds"))
            if candidate is not None:
                stale_candidates.append(candidate)
    sources.append(payload.get("mark_source"))
    existing_stale = _to_int(payload.get("stale_seconds"))
    if existing_stale is not None:
        stale_candidates.append(existing_stale)

    mark_source = _choose_best_mark_source(sources)
    if mark_source is not None:
        payload["mark_source"] = mark_source
    elif "mark_source" in payload:
        payload["mark_source"] = None

    if stale_candidates:
        stale_seconds = max(stale_candidates)
        payload["stale_seconds"] = stale_seconds
        payload["stale_s"] = stale_seconds


def _choose_best_mark_source(sources: Iterable[str | None]) -> str | None:
    best: str | None = None
    best_rank = math.inf
    for source in sources:
        canonical = _canonical_mark_source(source)
        if canonical is None:
            continue
        rank = _MARK_SOURCE_PRIORITY.get(canonical, math.inf)
        if rank < best_rank:
            best = canonical
            best_rank = rank
    return best


def _normalize_mark_payload(view: dict[str, Any], now: datetime) -> None:
    if not isinstance(view, dict):
        return
    now = _ensure_aware(now)
    single_stocks = view.get("single_stocks")
    if isinstance(single_stocks, list):
        for entry in single_stocks:
            if isinstance(entry, dict):
                _normalize_single_stock(entry, now)
    option_combos = view.get("option_combos")
    if isinstance(option_combos, list):
        for entry in option_combos:
            if not isinstance(entry, dict):
                continue
            _normalize_generic_mark_fields(entry)
            legs = entry.get("legs")
            if isinstance(legs, list):
                for leg in legs:
                    if isinstance(leg, dict):
                        _normalize_option_leg_entry(leg, now)
            _apply_combo_mark_metadata(entry)
    single_options = view.get("single_options")
    if isinstance(single_options, list):
        for entry in single_options:
            if not isinstance(entry, dict):
                continue
            _normalize_generic_mark_fields(entry, fields=("group_mark_source",))
            _normalize_option_leg_entry(entry, now)
    combo_groups = view.get("combo_groups")
    if isinstance(combo_groups, list):
        for entry in combo_groups:
            if isinstance(entry, dict):
                _normalize_generic_mark_fields(entry, fields=("mark_source",))
                _apply_combo_mark_metadata(entry)
                legs = entry.get("legs")
                if isinstance(legs, list):
                    for leg in legs:
                        if isinstance(leg, dict):
                            _normalize_option_mark_payload(leg, now=now)


def _normalize_single_stock(entry: dict[str, Any], now: datetime) -> None:
    _ensure_canonical_timestamp(entry, "bid_ts", _OPTION_BID_TS_ALIASES)
    _ensure_canonical_timestamp(entry, "ask_ts", _OPTION_ASK_TS_ALIASES)
    _ensure_canonical_timestamp(entry, "last_ts", _OPTION_LAST_TS_ALIASES)
    _ensure_canonical_timestamp(
        entry, "previous_close_ts", _OPTION_PREVIOUS_CLOSE_TS_ALIASES
    )
    mark_source = _canonical_mark_source(entry.get("mark_source"))
    if mark_source is not None:
        entry["mark_source"] = mark_source
        entry["price_source"] = _safe_lower(mark_source) or mark_source
    elif "mark_source" in entry:
        entry["mark_source"] = None
    stale_seconds = _resolve_stale_seconds_entry(entry, mark_source, now)
    if stale_seconds is not None:
        entry["stale_seconds"] = stale_seconds
        entry["stale_s"] = stale_seconds

    day_percent = _to_float(entry.get("day_pnl_percent"))
    if day_percent is None:
        day_percent = _to_float(entry.get("day_pnl_pct"))
    if day_percent is not None:
        entry["day_pnl_percent"] = day_percent
        entry["day_pnl_pct"] = day_percent

    if entry.get("pnl_unrealized") is None and entry.get("total_pnl") is not None:
        entry["pnl_unrealized"] = entry["total_pnl"]
    if entry.get("total_pnl") is None and entry.get("pnl_unrealized") is not None:
        entry["total_pnl"] = entry["pnl_unrealized"]

    unreal_percent = None
    for key in ("pnl_unrealized_percent", "pnl_unrealized_pct", "total_pnl_percent"):
        unreal_percent = _to_float(entry.get(key))
        if unreal_percent is not None:
            break
    if unreal_percent is not None:
        entry["pnl_unrealized_percent"] = unreal_percent
        entry["pnl_unrealized_pct"] = unreal_percent
        entry.setdefault("total_pnl_percent", unreal_percent)


_OPTION_BID_TS_ALIASES = (
    "bid_ts",
    "bidTs",
    "bid_timestamp",
    "bidTimestamp",
    "bidQuoteTime",
    "bidQuoteTs",
    "bidQuoteTimestamp",
    "bid_quote_time",
    "bid_quote_ts",
    "bid_quote_timestamp",
    "bid_time",
    "bidTime",
)
_OPTION_ASK_TS_ALIASES = (
    "ask_ts",
    "askTs",
    "ask_timestamp",
    "askTimestamp",
    "askQuoteTime",
    "askQuoteTs",
    "askQuoteTimestamp",
    "ask_quote_time",
    "ask_quote_ts",
    "ask_quote_timestamp",
    "ask_time",
    "askTime",
)
_OPTION_LAST_TS_ALIASES = (
    "last_ts",
    "lastTs",
    "last_timestamp",
    "lastTimestamp",
    "last_time",
    "lastTime",
    "lastTradeTimestamp",
    "lastTradeTs",
    "last_trade_timestamp",
    "last_trade_ts",
    "lastTradeTime",
    "last_trade_time",
    "trade_ts",
    "tradeTs",
    "tradeTimestamp",
    "trade_time",
    "tradeTime",
)
_OPTION_PREVIOUS_CLOSE_TS_ALIASES = (
    "previous_close_ts",
    "previousCloseTs",
    "previous_close_timestamp",
    "previousCloseTimestamp",
    "prior_close_ts",
    "priorCloseTs",
    "prior_close_timestamp",
    "priorCloseTimestamp",
    "prev_close_ts",
    "prevCloseTs",
    "prev_close_timestamp",
    "prevCloseTimestamp",
    "previous_close_at",
    "previousCloseAt",
    "prior_close_at",
    "priorCloseAt",
    "prev_close_at",
    "prevCloseAt",
    "prev_ts",
    "prevTs",
    "last_close_ts",
    "lastCloseTs",
    "last_close_timestamp",
    "lastCloseTimestamp",
)


def _is_numeric_zero(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return value == 0.0
    if isinstance(value, Decimal):
        if value.is_nan():
            return False
        return value == 0
    if isinstance(value, int):
        return value == 0
    return False


def _is_zeroish_string(value: str) -> bool:
    if value == "0":
        return True
    try:
        numeric = Decimal(value)
    except InvalidOperation:
        return False
    if numeric.is_nan():
        return True
    return numeric == 0


def _canon_ts_from_alias(entry: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if key not in entry:
            continue
        value = entry.get(key)
        if value is None:
            continue
        if isinstance(value, datetime):
            return _isoformat(value)
        if isinstance(value, float) and math.isnan(value):
            continue
        if isinstance(value, Decimal) and value.is_nan():
            continue
        if _is_numeric_zero(value):
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped or _is_zeroish_string(stripped):
                continue
            return stripped
        text = str(value).strip()
        if text and not _is_zeroish_string(text):
            return text
    return None


def _ensure_canonical_timestamp(
    entry: dict[str, Any], canonical_key: str, aliases: tuple[str, ...]
) -> None:
    current = entry.get(canonical_key)
    if isinstance(current, str):
        stripped = current.strip()
        if stripped and not _is_zeroish_string(stripped):
            return
    elif current is not None and not _is_numeric_zero(current):
        return
    candidate = _canon_ts_from_alias(entry, aliases)
    if candidate is not None:
        entry[canonical_key] = candidate


_OPTION_UPDATED_TIMESTAMP_KEYS = (
    "quote_updated_at",
    "quoteUpdatedAt",
    "updated_at",
    "updatedAt",
    "quote_timestamp",
    "quoteTimestamp",
    "quote_ts",
    "quoteTs",
    "quote_time",
    "quoteTime",
    "timestamp",
    "ts",
)

_OPTION_MID_TIMESTAMP_KEYS = (
    "mid_ts",
    "midTs",
    "mid_timestamp",
    "midTimestamp",
    "mid_time",
    "midTime",
    "bid_ts",
    "bidTs",
    "bid_timestamp",
    "bidTimestamp",
    "bidQuoteTs",
    "bidQuoteTimestamp",
    "bidQuoteTime",
    "bid_time",
    "bidTime",
    "bid_quote_time",
    "bid_quote_ts",
    "bid_quote_timestamp",
    "ask_ts",
    "askTs",
    "ask_timestamp",
    "askTimestamp",
    "askQuoteTs",
    "askQuoteTimestamp",
    "askQuoteTime",
    "ask_time",
    "askTime",
    "ask_quote_time",
    "ask_quote_ts",
    "ask_quote_timestamp",
)
_OPTION_LAST_TIMESTAMP_KEYS = (
    "last_ts",
    "lastTs",
    "last_timestamp",
    "lastTimestamp",
    "last_time",
    "lastTime",
    "last_trade_ts",
    "lastTradeTs",
    "last_trade_timestamp",
    "lastTradeTimestamp",
    "last_trade_time",
    "lastTradeTime",
    "trade_ts",
    "tradeTs",
    "trade_timestamp",
    "tradeTimestamp",
    "trade_time",
    "tradeTime",
)


def _normalize_option_leg_entry(entry: dict[str, Any], now: datetime) -> None:
    _normalize_option_mark_payload(entry, now=now)
    group_source = _canonical_mark_source(entry.get("group_mark_source"))
    if group_source is not None:
        entry["group_mark_source"] = group_source
    elif "group_mark_source" in entry:
        entry["group_mark_source"] = None


def _resolve_option_stale_seconds_entry(
    entry: dict[str, Any], mark_source: str | None, now: datetime
) -> int | None:
    """Return staleness in seconds based on the best available timestamp."""

    existing = _to_int(entry.get("stale_seconds"))
    if existing is None:
        existing = _to_int(entry.get("stale_s"))
    if existing == _PREV_STALE_FALLBACK_SECONDS:
        existing = None

    def _entry_value(key: str) -> Any:
        if isinstance(entry, dict):
            value = entry.get(key)
        else:  # pragma: no cover - defensive fallback for attr-style payloads
            value = getattr(entry, key, None)
        return value

    aware_now = _ensure_aware(now)

    if mark_source == "PREV":
        resolved = _resolve_stale_seconds_entry(entry, mark_source, aware_now)
        if resolved is not None:
            return resolved

    elif mark_source == "MID":
        timestamp = _latest_timestamp_from_entry(entry, _OPTION_MID_TIMESTAMP_KEYS)
        if timestamp is not None:
            return _seconds_between_datetimes(aware_now, timestamp)
        fallback = _extract_timestamp_from_entry(entry, _OPTION_UPDATED_TIMESTAMP_KEYS)
        if fallback is not None:
            return _seconds_between_datetimes(aware_now, fallback)

    elif mark_source == "LAST":
        timestamp = _extract_timestamp_from_entry(entry, _OPTION_LAST_TIMESTAMP_KEYS)
        if timestamp is not None:
            return _seconds_between_datetimes(aware_now, timestamp)
        fallback = _extract_timestamp_from_entry(entry, _OPTION_UPDATED_TIMESTAMP_KEYS)
        if fallback is not None:
            return _seconds_between_datetimes(aware_now, fallback)

    timestamp: datetime | None = None
    for key in ("ts", "last_ts", "prev_ts"):
        candidate = _entry_value(key)
        if candidate is None:
            continue
        parsed = _parse_timestamp_like(candidate)
        if parsed is not None:
            timestamp = parsed
            break

    if timestamp is not None:
        return _seconds_between_datetimes(aware_now, timestamp)

    return existing


def _latest_timestamp_from_entry(
    entry: dict[str, Any], keys: tuple[str, ...]
) -> datetime | None:
    latest: datetime | None = None
    for key in keys:
        ts = _parse_timestamp_like(entry.get(key))
        if ts is None:
            continue
        if latest is None or ts > latest:
            latest = ts
    return latest


def _extract_timestamp_from_entry(
    entry: dict[str, Any], keys: tuple[str, ...]
) -> datetime | None:
    for key in keys:
        if key in entry:
            ts = _parse_timestamp_like(entry.get(key))
            if ts is not None:
                return ts
    return None


def _seconds_between_datetimes(now: datetime, then: datetime) -> int:
    delta = now - then
    return int(max(delta.total_seconds(), 0))


def _normalize_generic_mark_fields(
    entry: dict[str, Any],
    *,
    fields: tuple[str, ...] = ("mark_source", "group_mark_source"),
) -> None:
    for field in fields:
        if field in entry:
            canonical = _canonical_mark_source(entry.get(field))
            if canonical is not None:
                entry[field] = canonical


def _resolve_stale_seconds_entry(
    entry: dict[str, Any], mark_source: str | None, now: datetime
) -> int | None:
    existing = _to_int(entry.get("stale_seconds"))
    if existing is None:
        existing = _to_int(entry.get("stale_s"))
    if existing == _PREV_STALE_FALLBACK_SECONDS:
        existing = None
    if mark_source != "PREV":
        return existing
    timestamp = _extract_previous_close_timestamp_from_entry(entry)
    if timestamp is not None:
        delta = now - timestamp
        return int(max(delta.total_seconds(), 0))
    if existing is not None:
        return existing
    return None


def _canonical_mark_source(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        upper = text.upper()
        return _MARK_SOURCE_ALIASES.get(upper, upper)
    return None


def _extract_previous_close_timestamp_from_entry(
    entry: dict[str, Any],
) -> datetime | None:
    for key in _OPTION_PREVIOUS_CLOSE_TS_ALIASES:
        if key in entry:
            ts = _parse_timestamp_like(entry.get(key))
            if ts is not None:
                return ts
    return None


_ZEROISH_TIMESTAMP_PATTERN = re.compile(r"^[+-]?(?:0+(?:\.0*)?|\.0+)(?:[eE][+-]?\d+)?$")


def _parse_timestamp_like(value: Any) -> datetime | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        seconds = float(value)
        if math.isnan(seconds):
            return None
        if seconds > 1e12:
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if _ZEROISH_TIMESTAMP_PATTERN.fullmatch(text):
        return None
    numeric_candidate: float | None
    try:
        numeric_candidate = float(text)
    except (TypeError, ValueError):
        numeric_candidate = None
    else:
        if math.isnan(numeric_candidate) or numeric_candidate == 0.0:
            return None
    iso_text = text
    if iso_text.endswith("Z") or iso_text.endswith("z"):
        iso_text = iso_text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(iso_text)
    except ValueError:
        parsed = None
    if parsed is not None:
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    if numeric_candidate is None:
        return None
    seconds = numeric_candidate
    if seconds > 1e12:
        seconds /= 1000.0
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


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


def _mark_or_fallback(mark: MarkResult, position: Position) -> Decimal:
    if mark.mark is not None:
        return Decimal(mark.mark)
    if position.avg_cost is not None:
        return position.avg_cost
    return Decimal("0")


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
