# SPDX-License-Identifier: MIT

"""OSI symbol parsing helpers shared across ingest and detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Final

_STRIKE_SCALE: Final = Decimal("1000")
_STRIKE_LEN: Final = 8
_TYPE_LEN: Final = 1
_EXPIRY_CANDIDATES: Final = (8, 6)


@dataclass(frozen=True)
class OsiParseResult:
    """Normalized metadata extracted from an OSI option symbol."""

    underlying: str
    expiry: date
    right: str
    strike: Decimal


def parse_osi(symbol: str | None) -> OsiParseResult | None:
    """Parse an OSI option symbol into normalized components.

    Supports both compact (``SPY251017C00445000``) and padded forms
    (``SPY  251017C00445000``). Expiry can be provided as ``YYMMDD`` or
    ``YYYYMMDD``. Returns ``None`` when the symbol does not resemble an OSI
    option identifier.
    """

    if not isinstance(symbol, str):
        return None

    sanitized = "".join(symbol.split()).upper()
    if not sanitized:
        return None

    for expiry_len in _EXPIRY_CANDIDATES:
        min_length = expiry_len + _TYPE_LEN + _STRIKE_LEN + 1
        if len(sanitized) < min_length:
            continue
        root_len = len(sanitized) - (expiry_len + _TYPE_LEN + _STRIKE_LEN)
        if not 1 <= root_len <= 6:
            continue
        strike_end = root_len + expiry_len + _TYPE_LEN + _STRIKE_LEN
        if strike_end != len(sanitized):
            continue

        root = sanitized[:root_len]
        expiry_digits = sanitized[root_len: root_len + expiry_len]
        option_type = sanitized[root_len + expiry_len]
        strike_digits = sanitized[root_len + expiry_len + _TYPE_LEN : strike_end]

        if option_type not in {"C", "P"}:
            continue
        if not expiry_digits.isdigit() or not strike_digits.isdigit():
            continue

        if expiry_len == 8:
            year = int(expiry_digits[:4])
            month = int(expiry_digits[4:6])
            day = int(expiry_digits[6:8])
        else:
            year_prefix = int(expiry_digits[:2])
            year = 1900 + year_prefix if year_prefix >= 70 else 2000 + year_prefix
            month = int(expiry_digits[2:4])
            day = int(expiry_digits[4:6])

        try:
            expiry_date = date(year, month, day)
        except ValueError:
            continue

        try:
            strike_value = Decimal(strike_digits) / _STRIKE_SCALE
        except (InvalidOperation, ValueError):
            continue

        right = "CALL" if option_type == "C" else "PUT"
        return OsiParseResult(underlying=root, expiry=expiry_date, right=right, strike=strike_value)

    # Legacy hyphen-delimited fallback (e.g. "AAPL-20240315-320-C")
    legacy = symbol.strip().upper()
    if "-" in legacy:
        parts = [part for part in legacy.split("-") if part]
        if len(parts) >= 4:
            root, expiry_text, strike_text, right_text = parts[:4]
            right_code = right_text[:1]
            if right_code not in {"C", "P"}:
                return None
            if not strike_text.replace(".", "", 1).isdigit():
                return None
            try:
                strike_value = Decimal(strike_text)
            except (InvalidOperation, ValueError):  # pragma: no cover - defensive
                return None
            parsed_expiry = _parse_expiry_digits(expiry_text)
            if parsed_expiry is None:
                return None
            expiry_date = parsed_expiry
            right = "CALL" if right_code == "C" else "PUT"
            return OsiParseResult(underlying=root, expiry=expiry_date, right=right, strike=strike_value)
    return None


def _parse_expiry_digits(value: str) -> date | None:
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) == 8:
        year = int(digits[:4])
        month = int(digits[4:6])
        day = int(digits[6:8])
    elif len(digits) == 6:
        year_prefix = int(digits[:2])
        year = 1900 + year_prefix if year_prefix >= 70 else 2000 + year_prefix
        month = int(digits[2:4])
        day = int(digits[4:6])
    else:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


__all__ = ["OsiParseResult", "parse_osi"]
