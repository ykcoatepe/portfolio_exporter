"""Universal PSD rules (v0.1)."""

from __future__ import annotations


def compute_1r(qty: int, entry: float, risk_per_unit: float | None = None) -> float:
    """Compute 1R for an instrument.

    If risk_per_unit is provided, 1R = |qty| * risk_per_unit, otherwise uses
    price-based unit risk of 1.0 for equities (placeholder).
    """
    if qty == 0:
        return 0.0
    if risk_per_unit is None:
        risk_per_unit = 1.0
    return abs(qty) * float(risk_per_unit)


def oco_levels(entry: float, one_r: float, stop_R: float, target_R: float) -> tuple[float, float]:
    """Return stop and target prices given entry, 1R and R-multipliers."""
    # Simplified: price change per R is proportional to one_r/qty; here we treat
    # one_r as the absolute risk currency and map to price deltas heuristically.
    # v0.1 toy: stop decreases by |stop_R|% of entry, target increases by target_R%.
    stop = entry * (1.0 + float(stop_R))
    target = entry * (1.0 + float(target_R))
    return (stop, target)


def credit_spread_tp_sl(credit: float, width: float, tp_capture: float) -> dict[str, float]:
    """Defined-risk credit spread TP/SL levels based on capture.

    - max_loss = width - credit
    - TP when debit <= credit * (1 - tp_capture)
    - SL when debit >= credit + max_loss
    Returns dict with {"tp_debit", "sl_debit", "max_loss"}.
    """
    max_loss = max(0.0, float(width) - float(credit))
    tp_debit = max(0.0, float(credit) * (1.0 - float(tp_capture)))
    sl_debit = float(credit) + max_loss
    return {"tp_debit": tp_debit, "sl_debit": sl_debit, "max_loss": max_loss}


def liquidity_guard(bid: float, ask: float, max_spread_mid: float) -> dict[str, float | bool]:
    mid = (float(bid) + float(ask)) / 2.0 if (bid or ask) else 0.0
    spread = float(ask) - float(bid)
    if mid <= 0:
        return {"warn": False, "spread_mid": 0.0}
    spread_mid = spread / mid
    return {"warn": spread_mid > float(max_spread_mid), "spread_mid": spread_mid}
