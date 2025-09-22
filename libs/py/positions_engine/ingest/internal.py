# SPDX-License-Identifier: MIT

"""Internal provider that reuses repo-local PSD snapshot helpers."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import subprocess
import sys
import threading
from collections.abc import Iterable
from copy import deepcopy
from datetime import date, datetime
from importlib import import_module
from inspect import isawaitable
from pathlib import Path
from typing import Any

from ..core.osi import parse_osi

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _ensure_repo_root() -> None:
    repo_str = str(_REPO_ROOT)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)


def _clean_symbol(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _iter_dicts(items: Any) -> Iterable[dict[str, Any]]:
    if isinstance(items, list):
        for entry in items:
            if isinstance(entry, dict):
                yield entry


def _copy_positions_view(view: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key in ("single_stocks", "option_combos", "single_options"):
        raw = view.get(key)
        if isinstance(raw, list):
            sanitized[key] = [
                deepcopy(entry) for entry in raw if isinstance(entry, dict)
            ]
        else:
            sanitized[key] = []
    for key, value in view.items():
        if key in sanitized:
            continue
        try:
            sanitized[key] = deepcopy(value)
        except (
            Exception
        ):  # pragma: no cover - defensive fallback for unserializable values
            sanitized[key] = value
    return sanitized


def _positions_view_counts(view: dict[str, Any]) -> tuple[int, int, int]:
    stocks = sum(1 for _ in _iter_dicts(view.get("single_stocks")))
    combos = sum(1 for _ in _iter_dicts(view.get("option_combos")))
    singles = sum(1 for _ in _iter_dicts(view.get("single_options")))
    return stocks, combos, singles


def _first_present(*values: Any) -> Any:
    for candidate in values:
        if candidate not in (None, ""):
            return candidate
    return None


def _to_float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return result


def _derive_single_stock_rows(
    positions: Iterable[dict[str, Any]],
    quotes: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    quote_map: dict[str, dict[str, Any]] = {}
    for quote in quotes:
        symbol = _clean_symbol(quote.get("symbol")) if isinstance(quote, dict) else None
        if symbol:
            quote_map[symbol] = quote

    rows: dict[str, dict[str, Any]] = {}
    for position in positions:
        if not isinstance(position, dict):
            continue
        symbol = _clean_symbol(position.get("symbol") or position.get("ticker"))
        if not symbol:
            continue
        inst_type = (
            str(position.get("instrument_type") or position.get("secType") or "")
            .strip()
            .lower()
        )
        if inst_type and inst_type not in {"equity", "stock", "stk"}:
            continue
        quantity = position.get(
            "quantity", position.get("qty", position.get("position"))
        )
        avg_cost = position.get(
            "avg_cost", position.get("average_cost", position.get("avgCost"))
        )
        base_entry = rows.setdefault(
            symbol,
            {
                "symbol": symbol,
                "qty": quantity if quantity is not None else 0,
                "avg_cost": avg_cost,
                "multiplier": position.get("multiplier", 1),
            },
        )
        if quantity is not None:
            base_entry["qty"] = quantity
        if avg_cost is not None:
            base_entry["avg_cost"] = avg_cost
        mark_candidate = _first_present(
            position.get("mark"),
            position.get("price"),
            position.get("last"),
            position.get("close"),
        )
        quote = quote_map.get(symbol)
        mark_source = "MISSING"
        if quote:
            bid_value = quote.get("bid")
            ask_value = quote.get("ask")
            base_entry.setdefault("bid", bid_value)
            base_entry.setdefault("ask", ask_value)
            mark_candidate = _first_present(mark_candidate, quote.get("last"))
            previous_close = _first_present(
                quote.get("previous_close"),
                quote.get("prior_close"),
                position.get("previous_close"),
            )
            if previous_close is not None:
                base_entry["previous_close"] = previous_close
            updated_at = _first_present(
                quote.get("updated_at"), quote.get("ts"), quote.get("timestamp")
            )
            if updated_at is not None:
                base_entry["updated_at"] = updated_at
            bid_float = _to_float_or_none(bid_value)
            ask_float = _to_float_or_none(ask_value)
            if (
                bid_float is not None
                and ask_float is not None
                and bid_float > 0
                and ask_float > 0
            ):
                mark_source = "MID"
            elif mark_candidate is not None:
                mark_source = "LAST"
            elif previous_close is not None:
                mark_source = "PREV"
        else:
            previous_close = position.get("previous_close")
            if previous_close is not None:
                base_entry["previous_close"] = previous_close
                if mark_candidate is None:
                    mark_source = "PREV"
            if mark_candidate is not None:
                mark_source = "LAST"
        if mark_candidate is not None:
            base_entry["mark"] = mark_candidate
        base_entry["mark_source"] = mark_source
        base_entry.setdefault("price_source", mark_source.lower())

    for entry in rows.values():
        qty_value = _to_float_or_none(entry.get("qty")) or 0.0
        multiplier = _to_float_or_none(entry.get("multiplier")) or 1.0
        mark_value = _to_float_or_none(entry.get("mark"))
        previous_close_value = _to_float_or_none(entry.get("previous_close"))
        avg_cost_value = _to_float_or_none(entry.get("avg_cost"))
        effective_qty = qty_value * multiplier
        day_basis = None
        if previous_close_value not in (None, 0):
            candidate = abs(effective_qty) * abs(previous_close_value)
            day_basis = candidate if candidate else None
        total_basis = None
        if avg_cost_value not in (None, 0):
            candidate = abs(effective_qty) * abs(avg_cost_value)
            total_basis = candidate if candidate else None
        if mark_value is not None and previous_close_value is not None:
            day_pnl = (mark_value - previous_close_value) * effective_qty
            entry["pnl_intraday"] = day_pnl
            if entry.get("day_pnl") in (None, ""):
                entry["day_pnl"] = day_pnl
            if day_basis and entry.get("day_pnl_percent") in (None, ""):
                entry["day_pnl_percent"] = day_pnl / day_basis
        if mark_value is not None and avg_cost_value is not None:
            total_pnl = (mark_value - avg_cost_value) * effective_qty
            entry["pnl_unrealized"] = total_pnl
            if entry.get("total_pnl") in (None, ""):
                entry["total_pnl"] = total_pnl
            if total_basis and entry.get("total_pnl_percent") in (None, ""):
                entry["total_pnl_percent"] = total_pnl / total_basis
        stale_value = entry.get("stale_s")
        if stale_value is None:
            stale_value = 0
        entry["stale_s"] = stale_value
        if entry.get("stale_seconds") in (None, ""):
            entry["stale_seconds"] = stale_value
    return list(rows.values())


class InternalScriptsProvider:
    """Resolve PSD snapshot helpers within the repository."""

    name = "internal"

    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = Path(repo_root) if repo_root else _REPO_ROOT
        self.source_detail: str | None = None
        self.positions_view: dict[str, Any] | None = None

    def load(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        self.source_detail = None
        self.positions_view = None
        try:
            snapshot = self._load_snapshot()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.info("Internal ingest skipped: %s", exc)
            return [], []
        if not snapshot:
            return [], []
        try:
            return self._normalize_snapshot(snapshot)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.info("Internal ingest skipped: %s", exc)
            return [], []

    def _load_snapshot(self) -> dict[str, Any] | None:
        _ensure_repo_root()

        for module_name, attr_candidates in (
            ("portfolio_exporter.psd_adapter", ("snapshot_once", "build_snapshot")),
            ("src.psd.ingestor.normalize", ("snapshot_once",)),
        ):
            module = self._import_optional(module_name)
            if module is None:
                continue
            for attr_name in attr_candidates:
                fn = getattr(module, attr_name, None)
                if not callable(fn):
                    continue
                result = self._invoke_callable(fn)
                if isinstance(result, dict) and result:
                    self.source_detail = f"{module_name}.{attr_name}"
                    return result

        for module_name in (
            "portfolio_exporter.psd_adapter",
            "src.psd.ingestor.normalize",
        ):
            snapshot = self._load_via_cli(module_name)
            if isinstance(snapshot, dict) and snapshot:
                self.source_detail = f"{module_name} (cli)"
                return snapshot

        return None

    def _import_optional(self, module_name: str) -> Any | None:
        try:
            return import_module(module_name)
        except ModuleNotFoundError:
            return None

    def _invoke_callable(self, fn: Any) -> Any:
        result = fn()
        if isawaitable(result):
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(result)
            container: dict[str, Any] = {}
            error: list[BaseException] = []

            def _runner() -> None:
                try:
                    container["value"] = asyncio.run(result)
                except BaseException as exc:  # pragma: no cover - defensive propagation
                    error.append(exc)

            thread = threading.Thread(target=_runner, daemon=True)
            thread.start()
            thread.join()
            if error:
                raise error[0]
            return container.get("value")
        return result

    def _load_via_cli(self, module_name: str) -> dict[str, Any] | None:
        try:
            proc = subprocess.run(
                [sys.executable, "-m", module_name, "--json"],
                check=True,
                capture_output=True,
                text=True,
                cwd=str(self._repo_root),
                timeout=30,
            )
        except (
            FileNotFoundError,
            subprocess.SubprocessError,
        ):  # pragma: no cover - defensive logging
            return None
        stdout = proc.stdout.strip()
        if not stdout:
            return None
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:  # pragma: no cover - defensive logging
            return None

    def _normalize_snapshot(
        self, snapshot: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        positions: list[dict[str, Any]] = []
        derived_quotes: list[dict[str, Any]] = []
        normalized_positions: list[dict[str, Any]] = []

        positions_view_payload = snapshot.get("positions_view")
        sanitized_view: dict[str, Any] | None = None
        if isinstance(positions_view_payload, dict):
            sanitized_view = _copy_positions_view(positions_view_payload)
            stock_rows, stock_quotes = self._from_positions_view(sanitized_view)
            positions.extend(stock_rows)
            derived_quotes.extend(stock_quotes)

        raw_positions = snapshot.get("positions")
        if isinstance(raw_positions, list):
            normalized_positions = [
                row for row in raw_positions if isinstance(row, dict)
            ]
            if normalized_positions and not positions:
                positions = normalized_positions.copy()

        quotes_payload = snapshot.get("quotes")
        quotes: list[dict[str, Any]] = []
        if isinstance(quotes_payload, dict):
            quotes = self._normalize_quotes_dict(quotes_payload)
        elif isinstance(quotes_payload, list):
            quotes = [row for row in quotes_payload if isinstance(row, dict)]

        if quotes:
            existing_symbols = {
                entry.get("symbol")
                for entry in quotes
                if isinstance(entry, dict) and entry.get("symbol")
            }
            for entry in derived_quotes:
                symbol = entry.get("symbol")
                if symbol and symbol not in existing_symbols:
                    quotes.append(entry)
        else:
            quotes = self._merge_quotes(derived_quotes, positions)

        view_for_logging = sanitized_view
        fallback_quotes = quotes or derived_quotes
        fallback_source = normalized_positions if normalized_positions else positions
        enriched_stocks = _derive_single_stock_rows(fallback_source, fallback_quotes)
        fallback_stocks: list[dict[str, Any]] = []

        if sanitized_view is None:
            if enriched_stocks:
                fallback_stocks = enriched_stocks
                view_for_logging = {
                    "single_stocks": [deepcopy(row) for row in enriched_stocks],
                    "option_combos": [],
                    "single_options": [],
                }
        elif not any(True for _ in _iter_dicts(sanitized_view.get("single_stocks"))):
            if enriched_stocks:
                fallback_stocks = enriched_stocks
                sanitized_view["single_stocks"] = [
                    deepcopy(row) for row in enriched_stocks
                ]
        else:
            if enriched_stocks:
                lookup = {
                    _clean_symbol(entry.get("symbol")): entry
                    for entry in enriched_stocks
                    if isinstance(entry, dict)
                }
                for stock in _iter_dicts(sanitized_view.get("single_stocks")):
                    symbol = _clean_symbol(stock.get("symbol"))
                    if not symbol:
                        continue
                    derived = lookup.get(symbol)
                    if not derived:
                        continue
                    for key in (
                        "mark",
                        "bid",
                        "ask",
                        "previous_close",
                        "updated_at",
                        "mark_source",
                        "price_source",
                        "pnl_intraday",
                        "pnl_unrealized",
                        "day_pnl",
                        "day_pnl_percent",
                        "total_pnl",
                        "total_pnl_percent",
                        "qty",
                        "avg_cost",
                        "stale_s",
                        "stale_seconds",
                    ):
                        if key not in stock or stock.get(key) in (None, ""):
                            value = derived.get(key)
                            if value is not None:
                                stock[key] = value
                    if stock.get("mark_source") in (None, ""):
                        stock["mark_source"] = derived.get("mark_source") or "MISSING"
                    if "price_source" not in stock and stock.get("mark_source"):
                        stock["price_source"] = str(stock["mark_source"]).lower()

        if sanitized_view is not None:
            view_for_logging = sanitized_view
            for stock in _iter_dicts(sanitized_view.get("single_stocks")):
                if stock.get("mark_source") in (None, ""):
                    stock["mark_source"] = "MISSING"
                if "price_source" not in stock and stock.get("mark_source"):
                    stock["price_source"] = str(stock["mark_source"]).lower()
                if stock.get("day_pnl") in (None, "") and stock.get(
                    "pnl_intraday"
                ) not in (None, ""):
                    stock["day_pnl"] = stock["pnl_intraday"]
                if stock.get("total_pnl") in (None, "") and stock.get(
                    "pnl_unrealized"
                ) not in (None, ""):
                    stock["total_pnl"] = stock["pnl_unrealized"]
                if stock.get("stale_seconds") in (None, ""):
                    stale_candidate = stock.get("stale_s")
                    if stale_candidate not in (None, ""):
                        stock["stale_seconds"] = stale_candidate

        if fallback_stocks:
            fallback_view_payload = {
                "single_stocks": fallback_stocks,
                "option_combos": [],
                "single_options": [],
            }
            fallback_positions, fallback_quote_rows = self._from_positions_view(
                fallback_view_payload
            )
            if fallback_positions:
                existing_equity_symbols = {
                    row.get("symbol")
                    for row in positions
                    if isinstance(row, dict) and row.get("symbol")
                }
                for entry in fallback_positions:
                    symbol = entry.get("symbol")
                    if symbol and symbol not in existing_equity_symbols:
                        positions.append(entry)
                        existing_equity_symbols.add(symbol)
            if fallback_quote_rows:
                if quotes:
                    known_quote_symbols = {
                        entry.get("symbol")
                        for entry in quotes
                        if isinstance(entry, dict) and entry.get("symbol")
                    }
                    for entry in fallback_quote_rows:
                        symbol = entry.get("symbol")
                        if symbol and symbol not in known_quote_symbols:
                            quotes.append(entry)
                            known_quote_symbols.add(symbol)
                else:
                    quotes = fallback_quote_rows

        if sanitized_view is not None:
            view_for_logging = sanitized_view

        self.positions_view = view_for_logging

        if self.positions_view is not None:
            stocks_count, combos_count, singles_count = _positions_view_counts(
                self.positions_view
            )
            detail = self.source_detail or "snapshot"
            if fallback_stocks:
                logger.info(
                    "[internal] positions_view stocks=%d combos=%d single_options=%d (fallback equities, source=%s)",
                    stocks_count,
                    combos_count,
                    singles_count,
                    detail,
                )
            else:
                logger.info(
                    "[internal] positions_view stocks=%d combos=%d single_options=%d (source=%s)",
                    stocks_count,
                    combos_count,
                    singles_count,
                    detail,
                )

        if not positions and not quotes:
            return [], []

        return positions, quotes

    def _from_positions_view(
        self, view: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        positions: list[dict[str, Any]] = []
        quotes: list[dict[str, Any]] = []

        for stock in _iter_dicts(view.get("single_stocks")):
            symbol = _clean_symbol(stock.get("symbol"))
            if not symbol:
                continue
            quantity = stock.get("qty", stock.get("quantity"))
            avg_cost = stock.get("avg_cost")
            if avg_cost is None:
                avg_cost = stock.get("mark")
            positions.append(
                {
                    "symbol": symbol,
                    "instrument_type": "equity",
                    "quantity": quantity if quantity is not None else 0,
                    "avg_cost": avg_cost if avg_cost is not None else 0.0,
                    "multiplier": stock.get("multiplier", 1),
                    "previous_close": stock.get("previous_close"),
                }
            )
            quotes.append(
                {
                    "symbol": symbol,
                    "bid": stock.get("bid"),
                    "ask": stock.get("ask"),
                    "last": stock.get("mark", stock.get("last")),
                    "previous_close": stock.get("previous_close"),
                    "updated_at": stock.get("updated_at") or stock.get("ts"),
                }
            )

        for combo in _iter_dicts(view.get("option_combos")):
            combo_underlying = combo.get("underlying")
            for leg in _iter_dicts(combo.get("legs")):
                record, leg_quote = self._option_leg_record(leg, combo_underlying)
                if record:
                    positions.append(record)
                if leg_quote:
                    quotes.append(leg_quote)

        for single_leg in _iter_dicts(view.get("single_options")):
            record, leg_quote = self._option_leg_record(
                single_leg, single_leg.get("underlying")
            )
            if record:
                positions.append(record)
            if leg_quote:
                quotes.append(leg_quote)

        return positions, quotes

    def _option_leg_record(
        self, leg: dict[str, Any], fallback_underlying: Any
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        symbol = _clean_symbol(leg.get("symbol")) or _clean_symbol(leg.get("contract"))
        if not symbol:
            symbol = _clean_symbol(leg.get("underlying"))
        if not symbol:
            return None, None
        greeks = leg.get("greeks") if isinstance(leg.get("greeks"), dict) else {}
        quantity = leg.get("quantity", leg.get("qty"))
        avg_cost = leg.get("avg_cost")
        if avg_cost is None:
            avg_cost = leg.get("entry_price") or leg.get("mark")

        multiplier = leg.get("multiplier", leg.get("contract_multiplier", 100))
        parsed_symbol = parse_osi(symbol)

        underlying_value = leg.get("underlying", fallback_underlying)
        expiry_value = leg.get("expiry")
        right_value = leg.get("right")
        strike_value = leg.get("strike")

        def _normalize_right(value: Any) -> str | None:
            if value in (None, ""):
                return None
            text = str(value).strip().upper()
            if text.startswith("C"):
                return "CALL"
            if text.startswith("P"):
                return "PUT"
            return text or None

        if parsed_symbol is not None:
            if underlying_value in (None, ""):
                underlying_value = parsed_symbol.underlying
            if expiry_value in (None, ""):
                expiry_value = parsed_symbol.expiry.isoformat()
            if right_value in (None, ""):
                right_value = parsed_symbol.right
            if strike_value in (None, ""):
                strike_value = float(parsed_symbol.strike)

        if isinstance(expiry_value, datetime):
            expiry_value = expiry_value.date().isoformat()
        elif isinstance(expiry_value, date):
            expiry_value = expiry_value.isoformat()
        elif isinstance(expiry_value, str):
            expiry_text = expiry_value.strip()
            if not expiry_text:
                expiry_value = (
                    parsed_symbol.expiry.isoformat()
                    if parsed_symbol is not None
                    else None
                )
            else:
                digits = "".join(ch for ch in expiry_text if ch.isdigit())
                if (
                    parsed_symbol is not None
                    and digits == expiry_text
                    and len(digits) in (6, 8)
                ):
                    expiry_value = parsed_symbol.expiry.isoformat()
                else:
                    expiry_value = expiry_text

        normalized_right = _normalize_right(right_value)
        if normalized_right is None and parsed_symbol is not None:
            normalized_right = parsed_symbol.right

        if isinstance(strike_value, str):
            strike_text = strike_value.strip()
            if strike_text:
                try:
                    strike_value = float(strike_text)
                except ValueError:
                    if parsed_symbol is not None:
                        strike_value = float(parsed_symbol.strike)
        elif isinstance(strike_value, (int, float)):
            strike_value = float(strike_value)
        elif strike_value is None and parsed_symbol is not None:
            strike_value = float(parsed_symbol.strike)

        underlying_clean = None
        if underlying_value not in (None, ""):
            underlying_clean = str(underlying_value).strip().upper()
        if underlying_clean in (None, "") and fallback_underlying not in (None, ""):
            underlying_clean = str(fallback_underlying).strip().upper()

        record: dict[str, Any] = {
            "symbol": symbol,
            "instrument_type": "option",
            "quantity": quantity if quantity is not None else 0,
            "avg_cost": avg_cost if avg_cost is not None else 0.0,
            "multiplier": multiplier if multiplier not in (None, "") else 100,
            "underlying": underlying_clean,
            "right": normalized_right,
            "strike": strike_value,
            "expiry": expiry_value,
            "delta": greeks.get("delta"),
            "theta": greeks.get("theta"),
        }
        quote: dict[str, Any] | None = None
        mark = leg.get("mark")
        bid = leg.get("bid")
        ask = leg.get("ask")
        if mark is not None or bid is not None or ask is not None:
            quote = {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "last": mark,
                "previous_close": leg.get("previous_close"),
                "updated_at": leg.get("updated_at") or leg.get("ts"),
            }
        return record, quote

    def _normalize_quotes_dict(self, quotes: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for symbol, payload in quotes.items():
            clean_symbol = _clean_symbol(symbol)
            if not clean_symbol:
                continue
            if isinstance(payload, dict):
                out.append(
                    {
                        "symbol": clean_symbol,
                        "bid": payload.get("bid"),
                        "ask": payload.get("ask"),
                        "last": payload.get("price")
                        or payload.get("mark")
                        or payload.get("last"),
                        "previous_close": payload.get("previous_close")
                        or payload.get("prior_close"),
                        "updated_at": payload.get("ts")
                        or payload.get("timestamp")
                        or payload.get("updated_at"),
                    }
                )
            else:
                out.append({"symbol": clean_symbol, "last": payload})
        return out

    def _merge_quotes(
        self,
        derived: list[dict[str, Any]],
        positions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for entry in derived:
            symbol = entry.get("symbol")
            if symbol:
                merged[symbol] = entry
        for position in positions:
            symbol = position.get("symbol")
            if not symbol or symbol in merged:
                continue
            last = position.get("mark") or position.get("price")
            merged[symbol] = {"symbol": symbol, "last": last}
        return list(merged.values())
