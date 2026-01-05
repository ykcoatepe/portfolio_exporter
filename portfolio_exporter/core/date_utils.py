"""Date parsing helpers to avoid ambiguous year warnings."""

from __future__ import annotations

import datetime as _dt
import re as _re

_YEAR_RE = _re.compile(r"\b\d{4}\b")
_FULL_DATE_RE = _re.compile(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b")
_NUMERIC_RE = _re.compile(r"^(?P<a>\d{1,2})[./-](?P<b>\d{1,2})$")

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_MONTH_FIRST_RE = _re.compile(
    r"^(?P<month>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"[\s./-]?(?P<day>\d{1,2})$",
    _re.IGNORECASE,
)
_DAY_FIRST_RE = _re.compile(
    r"^(?P<day>\d{1,2})[\s./-]?"
    r"(?P<month>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)$",
    _re.IGNORECASE,
)


def utcnow() -> _dt.datetime:
    """Return naive UTC datetime (avoids datetime.utcnow deprecation)."""

    return _dt.datetime.now(tz=_dt.UTC).replace(tzinfo=None)


def _candidate_from_parts(month: int, day: int, base: _dt.date) -> _dt.date | None:
    try:
        candidate = _dt.date(base.year, month, day)
    except ValueError:
        return None
    if candidate < base:
        try:
            candidate = _dt.date(base.year + 1, month, day)
        except ValueError:
            return None
    return candidate


def parse_month_day_no_year(
    text: str, base_date: _dt.date | None = None
) -> _dt.date | None:
    """Parse month/day strings that omit the year.

    Returns a date using the base year (or next year if already passed).
    Returns None when a year appears to be present.
    """

    if not text:
        return None
    raw = text.strip()
    if not raw:
        return None
    if _YEAR_RE.search(raw) or _FULL_DATE_RE.search(raw):
        return None

    base = base_date or _dt.date.today()
    candidates: list[_dt.date] = []

    token = raw.replace(",", " ").strip().lower()
    m = _MONTH_FIRST_RE.match(token)
    if m:
        month = _MONTHS[m.group("month")]
        day = int(m.group("day"))
        candidate = _candidate_from_parts(month, day, base)
        if candidate is not None:
            candidates.append(candidate)

    m = _DAY_FIRST_RE.match(token)
    if m:
        month = _MONTHS[m.group("month")]
        day = int(m.group("day"))
        candidate = _candidate_from_parts(month, day, base)
        if candidate is not None:
            candidates.append(candidate)

    m = _NUMERIC_RE.match(token)
    if m:
        first = int(m.group("a"))
        second = int(m.group("b"))
        for month, day in ((first, second), (second, first)):
            if not (1 <= month <= 12 and 1 <= day <= 31):
                continue
            candidate = _candidate_from_parts(month, day, base)
            if candidate is not None:
                candidates.append(candidate)

    return min(candidates) if candidates else None
