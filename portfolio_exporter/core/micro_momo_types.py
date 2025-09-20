from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ScanRow:
    symbol: str
    price: float
    volume: int
    rel_strength: float
    short_interest: float
    turnover: float
    iv_rank: float
    atr_pct: float
    trend: float

    @staticmethod
    def from_csv_row(row: dict[str, str]) -> ScanRow:
        def f(name: str, default: float = 0.0) -> float:
            try:
                return float(row.get(name, default))
            except (TypeError, ValueError):
                return float(default)

        def i(name: str, default: int = 0) -> int:
            try:
                return int(float(row.get(name, default)))
            except (TypeError, ValueError):
                return int(default)

        return ScanRow(
            symbol=str(row.get("symbol", "")).upper(),
            price=f("price"),
            volume=i("volume"),
            rel_strength=f("rel_strength"),
            short_interest=f("short_interest"),
            turnover=f("turnover"),
            iv_rank=f("iv_rank"),
            atr_pct=f("atr_pct"),
            trend=f("trend"),
        )


@dataclass
class ChainRow:
    symbol: str
    expiry: str  # YYYYMMDD
    right: str  # C or P
    strike: float
    bid: float
    ask: float
    last: float
    volume: int
    oi: int

    @property
    def mid(self) -> float:
        if self.ask > 0 and self.bid > 0:
            return (self.bid + self.ask) / 2
        if self.ask > 0:
            return self.ask
        if self.bid > 0:
            return self.bid
        return self.last


@dataclass
class Structure:
    template: str  # DebitCall | BearCallCredit | Template
    expiry: str | None
    long_strike: float | None
    short_strike: float | None
    debit_or_credit: str | None  # debit | credit
    width: float | None
    per_leg_oi_ok: bool
    per_leg_spread_pct: float | None
    needs_chain: bool
    limit_price: float | None


@dataclass
class ResultRow:
    symbol: str
    raw_score: float
    tier: str
    passes_core_filter: bool
    direction: str
    structure_template: str
    contracts: int
    entry_trigger: float | str
    tp: float
    sl: float
    expiry: str | None
    long_strike: float | None
    short_strike: float | None
    debit_or_credit: str | None
    width: float | None
    per_leg_oi_ok: bool
    per_leg_spread_pct: float | None
    needs_chain: bool

    def to_orders_csv(self) -> dict[str, Any]:
        long_leg = f"C {self.long_strike}" if self.long_strike is not None else ""
        short_leg = f"C {self.short_strike}" if self.short_strike is not None else ""
        structure = self.structure_template
        return {
            "symbol": self.symbol,
            "tier": self.tier,
            "direction": self.direction,
            "structure": structure,
            "contracts": self.contracts,
            "expiry": self.expiry or "",
            "long_leg": long_leg,
            "short_leg": short_leg,
            "limit": "",
            "OCO_tp": self.tp,
            "OCO_sl": self.sl,
            "entry_trigger": self.entry_trigger,
            "notes": "",
        }
