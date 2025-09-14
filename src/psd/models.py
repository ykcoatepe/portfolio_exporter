"""PSD domain models (v0.1).

Minimal, typed dataclasses used by the sentinel. These intentionally avoid
runtime-heavy imports and perform lightweight validation only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


Sleeve = Literal["core", "momo", "alpha", "theta", "alts", "meme"]
Severity = Literal["info", "warn", "action"]
Kind = Literal["equity", "option", "credit_spread", "iron_condor"]


@dataclass(slots=True)
class OptionLeg:
    symbol: str
    expiry: str  # YYYYMMDD
    right: Literal["C", "P"]
    strike: float
    qty: int
    price: float
    delta: float | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("OptionLeg.symbol required")
        if self.strike <= 0:
            raise ValueError("OptionLeg.strike must be > 0")
        if self.qty == 0:
            raise ValueError("OptionLeg.qty must be non-zero")
        if self.price < 0:
            raise ValueError("OptionLeg.price cannot be negative")


@dataclass(slots=True)
class Position:
    uid: str
    symbol: str
    sleeve: Sleeve
    kind: Kind
    qty: int
    mark: float
    beta: float | None = None
    # for options
    legs: list[OptionLeg] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.uid:
            raise ValueError("Position.uid required")
        if not self.symbol:
            raise ValueError("Position.symbol required")
        if self.mark < 0:
            raise ValueError("Position.mark cannot be negative")
        if self.kind in ("credit_spread", "iron_condor") and not self.legs:
            raise ValueError("Defined-risk positions require legs")


@dataclass(slots=True)
class RiskSnapshot:
    nav: float
    vix: float
    delta_beta: float | None = None
    var95_1d: float | None = None
    margin_used: float | None = None  # 0..1 of max

    def __post_init__(self) -> None:
        if self.nav <= 0:
            raise ValueError("RiskSnapshot.nav must be > 0")
        if self.vix < 0:
            raise ValueError("RiskSnapshot.vix cannot be negative")


@dataclass(slots=True)
class Alert:
    uid: str
    rule: str
    severity: Severity
    message: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Memo:
    ts: int
    uid: str
    rule: str
    severity: Severity
    snapshot: Dict[str, Any]
    suggestion: Optional[str] = None
