from __future__ import annotations

"""Budget checks for theta and hedges (v0.3)."""


def theta_weekly_fees(
    nav: float, fees_week_to_date: float, threshold: float | None = None
) -> dict[str, float | bool]:
    """Warn when weekly theta fees exceed threshold fraction of NAV.

    threshold: fraction (e.g., 0.001 for 0.10%). Defaults to 0.001.
    Returns {warn: bool, burn: float} where burn is fraction of NAV.
    """
    thr = 0.001 if threshold is None else float(threshold)
    burn = 0.0 if nav <= 0 else float(fees_week_to_date) / float(nav)
    return {"warn": burn > thr, "burn": burn}


def hedge_monthly_carry(
    nav: float, hedge_cost_mtd: float, cap: float | None = None
) -> dict[str, float | bool]:
    """Warn when monthly hedge carry exceeds cap fraction of NAV.

    cap: fraction (e.g., 0.0035 for 0.35%). Defaults to 0.0035.
    Returns {warn: bool, burn: float} where burn is fraction of NAV.
    """
    limit = 0.0035 if cap is None else float(cap)
    burn = 0.0 if nav <= 0 else float(hedge_cost_mtd) / float(nav)
    return {"warn": burn > limit, "burn": burn}


def footer_dto(
    nav: float, fees_wtd: float, hedge_mtd: float, thresholds: dict[str, float] | None = None
) -> dict[str, object]:
    t = thresholds or {}
    th = theta_weekly_fees(nav, fees_wtd, t.get("theta_weekly"))
    hc = hedge_monthly_carry(nav, hedge_mtd, t.get("hedge_monthly"))
    return {
        "theta": th,
        "hedge": hc,
    }
