from __future__ import annotations

from typing import Any, Dict, Tuple

from .micro_momo_types import ResultRow, ScanRow, Structure
from .micro_momo_utils import clamp, inv_scale, scale, to_bool


def _get(row: Any, name: str, default: float | int | str | None = None) -> Any:
    # Flexible getter for dataclass/dict/namespace
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def passes_filters(row: ScanRow, cfg: Dict[str, object]) -> bool:
    f = cfg.get("filters", {})  # type: ignore[assignment]

    # price bounds
    pb = f.get("price_bounds", {})  # type: ignore[assignment]
    last_price = float(_get(row, "last_price", getattr(row, "price", 0.0)))
    min_px = float(pb.get("min", 5.0))  # type: ignore[union-attr]
    max_px = float(pb.get("max", 500.0))  # type: ignore[union-attr]
    if not (min_px <= last_price <= max_px):
        return False

    # float <= float_max_millions
    float_max = float(f.get("float_max_millions", 2000.0))  # type: ignore[union-attr]
    fm_val = _get(row, "float_millions", None)
    if fm_val is not None and fm_val != "":
        float_millions = float(fm_val)
        if float_millions > float_max:
            return False

    # ADV USD >= adv_usd_min_millions
    adv_min = float(f.get("adv_usd_min_millions", 5.0))  # type: ignore[union-attr]
    adv_val = _get(row, "adv_usd_millions", None)
    if adv_val is not None and adv_val != "":
        adv_usd_millions = float(adv_val)
        if adv_usd_millions < adv_min:
            return False

    # premkt gap >= premkt_gap_min_pct
    gap_min = float(f.get("premkt_gap_min_pct", 0.0))  # type: ignore[union-attr]
    gap_val = _get(row, "premkt_gap_pct", None)
    if gap_val is not None and gap_val != "":
        premkt_gap_pct = float(gap_val)
        if premkt_gap_pct < gap_min:
            return False

    # rvol_1m >= rvol_min
    rvol_min = float(f.get("rvol_min", 1.0))  # type: ignore[union-attr]
    rvol1_val = _get(row, "rvol_1m", None)
    if rvol1_val is not None and rvol1_val != "":
        rvol_1m = float(rvol1_val)
        if rvol_1m < rvol_min:
            return False

    # optionable == Yes
    opt_val = _get(row, "optionable", None)
    if opt_val is not None and str(opt_val) != "":
        if not (str(opt_val).strip().lower() == "yes"):
            return False

    # near-money OI >= threshold
    near_money_oi_min = int(f.get("near_money_oi_min", 50))  # type: ignore[union-attr]
    oi_val = _get(row, "oi_near_money", None)
    if oi_val is not None and oi_val != "":
        oi_near = float(oi_val)
        if oi_near < near_money_oi_min:
            return False

    # spread pct near money <= max pct
    spread_max = float(f.get("opt_spread_max_pct", 0.05))  # type: ignore[union-attr]
    sp_val = _get(row, "spread_pct_near_money", None)
    if sp_val is not None and sp_val != "":
        spread_nm = float(sp_val)
        if spread_nm > spread_max:
            return False

    # halts count today <= max
    halts_max = int(f.get("halts_max", 0))  # type: ignore[union-attr]
    halts_val = _get(row, "halts_count_today", None)
    if halts_val is not None and halts_val != "":
        halts = int(float(halts_val))
        if halts > halts_max:
            return False

    return True


def score_components(row: ScanRow, cfg: Dict[str, object]) -> Tuple[Dict[str, float], float]:
    w = cfg.get("weights", {})  # type: ignore[assignment]

    # gap: 0→20% mapped to 0→100
    gap_pct = float(_get(row, "premkt_gap_pct", 0.0))
    comp_gap = clamp(scale(gap_pct, 0.0, 20.0) * 100.0, 0.0, 100.0)

    # rvol: avg(rvol_1m, rvol_5m) mapped 1→5 to 0→100
    r1 = float(_get(row, "rvol_1m", 1.0))
    r5 = float(_get(row, "rvol_5m", r1))
    rvol_avg = (r1 + r5) / 2.0
    comp_rvol = clamp(scale(rvol_avg, 1.0, 5.0) * 100.0, 0.0, 100.0)

    # float: smaller is better [0..float_max] -> [100..0]
    fmax = float(cfg.get("filters", {}).get("float_max_millions", 2000.0))  # type: ignore[union-attr]
    fval = float(_get(row, "float_millions", 0.0))
    comp_float = clamp(inv_scale(fval, 0.0, fmax) * 100.0, 0.0, 100.0)

    # short interest: 0→25% -> 0→100
    short_pct = float(_get(row, "short_interest_pct", _get(row, "short_interest", 0.0)))
    comp_short = clamp(scale(short_pct, 0.0, 25.0) * 100.0, 0.0, 100.0)

    # liquidity: ADV$ from adv_min → 200 mapped 0→100
    adv_min = float(cfg.get("filters", {}).get("adv_usd_min_millions", 5.0))  # type: ignore[union-attr]
    adv = float(_get(row, "adv_usd_millions", 0.0))
    comp_liq = clamp(scale(adv, adv_min, 200.0) * 100.0, 0.0, 100.0)

    # options_quality: average of OI_subscore and spread_subscore; 0 if not optionable
    optionable = str(_get(row, "optionable", "No")).strip().lower() == "yes"
    near_money_oi_min = float(cfg.get("filters", {}).get("near_money_oi_min", 50.0))  # type: ignore[union-attr]
    oi_near = float(_get(row, "oi_near_money", 0.0))
    oi_sub = clamp(scale(oi_near, near_money_oi_min, 1000.0) * 100.0, 0.0, 100.0)
    spread_max = float(cfg.get("filters", {}).get("opt_spread_max_pct", 0.05))  # type: ignore[union-attr]
    spread_nm = float(_get(row, "spread_pct_near_money", spread_max))
    spread_sub = clamp(inv_scale(spread_nm, 0.0, spread_max) * 100.0, 0.0, 100.0)
    comp_opt = (oi_sub + spread_sub) / 2.0 if optionable else 0.0

    # vwap: inverse distance map (0→5% → 100→0) +15 if above_vwap_now==Yes
    last_px = float(_get(row, "last_price", getattr(row, "price", 0.0)))
    vwap = float(_get(row, "vwap", last_px))
    dist_pct = abs((last_px - vwap) / vwap) if vwap else 1.0
    base_vwap = clamp(inv_scale(dist_pct, 0.0, 0.05) * 100.0, 0.0, 100.0)
    above_now = str(_get(row, "above_vwap_now", "No")).strip().lower() == "yes"
    comp_vwap = clamp(base_vwap + (15.0 if above_now else 0.0), 0.0, 100.0)

    # pattern: contains reclaim|orb|hod → 70/60/50 else 0
    patt = str(_get(row, "pattern_signal", "")).lower()
    if "reclaim" in patt:
        comp_pattern = 70.0
    elif "orb" in patt:
        comp_pattern = 60.0
    elif "hod" in patt:
        comp_pattern = 50.0
    else:
        comp_pattern = 0.0

    # news_buzz: +50 if news_catalyst present + min(50, social_buzz_score_1h*0.8)
    news_present = str(_get(row, "news_catalyst", "")).strip() != ""
    buzz = float(_get(row, "social_buzz_score_1h", 0.0))
    comp_news = 0.0
    if news_present:
        comp_news = min(100.0, 50.0 + min(50.0, buzz * 0.8))

    comps = {
        "gap": comp_gap,
        "rvol": comp_rvol,
        "float": comp_float,
        "short": comp_short,
        "liquidity": comp_liq,
        "options_quality": comp_opt,
        "vwap": comp_vwap,
        "pattern": comp_pattern,
        "news_buzz": comp_news,
    }

    # weighted average per cfg["weights"]
    total_w = 0.0
    acc = 0.0
    for k, v in comps.items():
        wk = float(w.get(k, 1.0))  # type: ignore[union-attr]
        acc += wk * v
        total_w += wk
    raw = 0.0 if total_w <= 0 else acc / total_w
    raw = clamp(round(raw, 1), 0.0, 100.0)
    return comps, raw


def tier_and_dir(row: ScanRow, raw_score: float, cfg: Dict[str, object]) -> Tuple[str, str]:
    # Tiering
    t_cfg = cfg.get("tiers", {})  # type: ignore[assignment]
    a_thr = float(t_cfg.get("A_tier", 75.0))  # type: ignore[union-attr]
    b_thr = float(t_cfg.get("B_tier", 55.0))  # type: ignore[union-attr]
    pf = passes_filters(row, cfg)
    if raw_score >= a_thr and pf:
        tier = "A"
    elif raw_score >= b_thr:
        tier = "B"
    else:
        tier = "C"

    # Direction
    patt = str(_get(row, "pattern_signal", "")).lower()
    above_now = str(_get(row, "above_vwap_now", "")).lower() == "yes"
    if above_now and ("reclaim" in patt or "orb" in patt or "hod" in patt):
        direction = "long"
    elif (str(_get(row, "above_vwap_now", "")).lower() == "no") and ("fail" in patt):
        direction = "short"
    else:
        direction = "long?"
    return tier, direction


def size_and_targets(struct: Structure, row: ScanRow, cfg: Dict[str, object]) -> Tuple[int, float, float]:
    s_cfg = cfg.get("sizing", {})  # type: ignore[assignment]
    risk_budget = float(s_cfg.get("risk_budget", 250.0))  # type: ignore[union-attr]
    max_contracts = int(s_cfg.get("max_contracts", 5))  # type: ignore[union-attr]

    px = struct.limit_price if (struct.limit_price and struct.limit_price > 0) else 1.0
    # Options are per 100 multiplier
    risk_per_contract = px * 100.0
    contracts = max(1, min(max_contracts, int(risk_budget // max(1.0, risk_per_contract))))
    # If risk_per_contract < 1 we could end up with too many; clamp to max
    contracts = min(max_contracts, max(1, contracts))

    t_cfg = cfg.get("targets", {})  # type: ignore[assignment]
    tp_pct = float(t_cfg.get("tp_pct", 0.5))  # type: ignore[union-attr]
    sl_pct = float(t_cfg.get("sl_pct", 0.5))  # type: ignore[union-attr]
    tp = round(px * (1.0 + tp_pct), 2)
    sl = round(px * (1.0 - sl_pct), 2)
    return contracts, tp, sl


def entry_trigger(direction: str, row: ScanRow, cfg: Dict[str, object]) -> str | float:
    confirm = cfg.get("rvol_confirm_entry", 1.5)  # type: ignore[assignment]
    vwap = _get(row, "vwap", "NA")
    orb_high = _get(row, "orb_high", "NA")
    if direction == "long":
        return (
            f"ORB break → pullback to VWAP → reclaim (RVOL ≥ {confirm}); levels: orb={orb_high}, vwap={vwap}"
        )
    return (
        f"Lower-high → VWAP rejection (no fresh halt) (RVOL ≥ {confirm}); levels: vwap={vwap}"
    )
