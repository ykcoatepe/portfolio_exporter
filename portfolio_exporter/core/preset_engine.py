from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

from portfolio_exporter.core.ib import quote_option, quote_stock, net_liq as _ib_net_liq


@dataclass
class LiquidityRules:
    min_oi: int = 200
    min_volume: int = 50
    max_spread_pct: float = 0.02  # 2% of mid


@dataclass
class Profile:
    name: str
    target_delta: float  # absolute, e.g. 0.16
    width: float = 5.0


PROFILES = [
    Profile("conservative", 0.14, 5.0),
    Profile("balanced", 0.18, 5.0),
    Profile("aggressive", 0.26, 5.0),
]


def _pick_profile(name: str | None) -> Profile:
    if not name:
        return PROFILES[1]
    name = name.lower()
    for p in PROFILES:
        if p.name.startswith(name):
            return p
    return PROFILES[1]


def _compute_t_days(expiry: str) -> int:
    from datetime import date

    return (date.fromisoformat(expiry) - date.today()).days


def _expected_move(spot: float, iv: float, dte: int) -> float:
    # iv as decimal (e.g., 0.25)
    return spot * iv * math.sqrt(max(dte, 1) / 365)


def _earnings_near(symbol: str, expiry: str, window_days: int = 7) -> bool:
    """Return True if an earnings date is within +/- window_days of expiry.

    Tries yfinance.get_earnings_dates; falls back to Ticker.calendar if needed.
    If data is unavailable, returns False (do not block).
    """
    from datetime import date, timedelta

    try:
        tkr = yf.Ticker(symbol)
        try:
            df = tkr.get_earnings_dates(limit=12)
            if df is not None and not df.empty:
                edates = [d.date() for d in pd.to_datetime(df.index)]
            else:
                edates = []
        except Exception:
            cal = getattr(tkr, "calendar", None)
            edates = []
            if isinstance(cal, pd.DataFrame) and not cal.empty:
                for col in cal.columns:
                    if "Earnings" in str(col) or "Earnings Date" in str(col):
                        try:
                            ed = pd.to_datetime(cal[col].iloc[0]).date()
                            edates.append(ed)
                        except Exception:
                            pass
        if not edates:
            return False
        exp = pd.to_datetime(expiry).date()
        for d in edates:
            if abs((d - exp).days) <= window_days:
                return True
        return False
    except Exception:
        return False


def _spread_pct(bid: float, ask: float, mid: float) -> float:
    if not mid or mid <= 0:
        return 1.0
    if bid is None or ask is None:
        return 1.0
    return max(0.0, (ask - bid) / mid)


def _nearest_yf_expiry(symbol: str, expiry: str) -> Tuple[str, list[str]]:
    """Return an expiry present in Yahoo's options list, preferring the same date,
    else the next later available date, else the last available.
    """
    tkr = yf.Ticker(symbol)
    exps = list(tkr.options or [])
    if not exps:
        return expiry, []
    if expiry in exps:
        return expiry, exps
    for d in exps:
        if d >= expiry:
            return d, exps
    return exps[-1], exps


def _yf_chain(symbol: str, expiry: str) -> Tuple[pd.DataFrame, pd.DataFrame, float, str]:
    tkr = yf.Ticker(symbol)
    spot = tkr.history(period="1d")["Close"].iloc[-1]
    resolved, _ = _nearest_yf_expiry(symbol, expiry)
    chain = tkr.option_chain(resolved)
    calls = chain.calls.copy()
    puts = chain.puts.copy()
    # Ensure columns exist
    for df in (calls, puts):
        for col in ("bid", "ask", "impliedVolatility", "openInterest", "volume"):
            if col not in df.columns:
                df[col] = 0.0
    return calls, puts, float(spot), resolved


def _add_delta(df: pd.DataFrame, spot: float, dte: int, right: str) -> pd.DataFrame:
    # Compute Black-Scholes delta using IV and DTE; normalized [-1..1]
    import numpy as np

    def norm_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def row_delta(row):
        iv = float(row.get("impliedVolatility") or 0.0)
        if not iv or math.isnan(iv):
            return np.nan
        t = max(dte, 1) / 365
        try:
            d1 = (math.log(spot / float(row["strike"])) + (0.01 + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
        except Exception:
            return np.nan
        if right == "C":
            return norm_cdf(d1)
        else:
            return norm_cdf(d1) - 1.0

    out = df.copy()
    out["delta"] = out.apply(row_delta, axis=1)
    # Mid and spread
    out["mid"] = (out["bid"] + out["ask"]) / 2
    out["spread_pct"] = (out["ask"] - out["bid"]) / out["mid"].replace(0, float("nan"))
    return out


def _filter_liquidity(df: pd.DataFrame, rules: LiquidityRules) -> pd.DataFrame:
    return df[(df["openInterest"] >= rules.min_oi) & (df["volume"] >= rules.min_volume) & (df["spread_pct"] <= rules.max_spread_pct)]


def _nearest_strike(strikes: List[float], target: float) -> float:
    return min(strikes, key=lambda k: abs(k - target))


def _price_leg(symbol: str, expiry: str, strike: float, right: str) -> Dict[str, float]:
    try:
        return quote_option(symbol, expiry, strike, right)
    except Exception:
        return {"mid": 0.0, "bid": 0.0, "ask": 0.0}


def _mid_from_df(df: Optional[pd.DataFrame], strike: float) -> Optional[float]:
    if df is None:
        return None
    try:
        row = df.loc[(df["strike"].astype(float) == float(strike))].iloc[0]
        bid = float(row.get("bid", 0.0))
        ask = float(row.get("ask", 0.0))
        mid = (bid + ask) / 2 if (bid and ask) else float(row.get("mid", 0.0))
        return float(mid)
    except Exception:
        return None


def suggest_credit_vertical(
    symbol: str,
    expiry: str,
    side: str,  # 'bull_put' or 'bear_call'
    profile: str | None = None,
    rules: LiquidityRules | None = None,
    *,
    df_calls: Optional[pd.DataFrame] = None,
    df_puts: Optional[pd.DataFrame] = None,
    spot_override: Optional[float] = None,
    avoid_earnings: bool = True,
    earnings_window_days: int = 7,
    risk_budget_pct: Optional[float] = None,
    netliq: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Return up to 3 candidate credit verticals using target delta profiles.

    Each candidate contains: legs, credit, max_loss, pop_proxy, breakevens,
    liquidity flags, EM context and a brief rationale.
    """
    profs = [
        _pick_profile("conservative"),
        _pick_profile("balanced"),
        _pick_profile("aggressive"),
    ]
    if profile:
        # ensure requested profile appears first
        sel = _pick_profile(profile)
        profs = [sel] + [p for p in profs if p.name != sel.name]

    rules = rules or LiquidityRules()
    if df_calls is None or df_puts is None or spot_override is None:
        calls, puts, spot, expiry_resolved = _yf_chain(symbol, expiry)
    else:
        calls, puts, spot, expiry_resolved = df_calls.copy(), df_puts.copy(), float(spot_override), expiry
    # Use the resolved expiry for downstream pricing/labels
    expiry = expiry_resolved
    if avoid_earnings and _earnings_near(symbol, expiry, earnings_window_days):
        return []
    dte = _compute_t_days(expiry)
    calls = _add_delta(calls, spot, dte, "C")
    puts = _add_delta(puts, spot, dte, "P")
    calls = _filter_liquidity(calls, rules)
    puts = _filter_liquidity(puts, rules)

    em = _expected_move(spot, float(calls["impliedVolatility"].median() or 0.25), dte)

    results: List[Dict[str, Any]] = []
    if side not in {"bull_put", "bear_call"}:
        return results

    if side == "bull_put":
        df = puts.dropna(subset=["delta"]).copy()
        df["delta_abs"] = df["delta"].abs()
        right = "P"
        width_sign = -1  # long lower strike
    else:
        df = calls.dropna(subset=["delta"]).copy()
        df["delta_abs"] = df["delta"].abs()
        right = "C"
        width_sign = 1  # long higher strike

    all_strikes = sorted(df["strike"].astype(float).unique().tolist())

    for p in profs:
        # Pick short strike closest to target delta
        df_sorted = df.iloc[(df["delta_abs"] - p.target_delta).abs().argsort()]
        if df_sorted.empty:
            continue
        short_row = df_sorted.iloc[0]
        k_short = float(short_row["strike"])
        k_long_target = k_short + width_sign * float(p.width)
        k_long = _nearest_strike(all_strikes, k_long_target)
        if k_long == k_short:
            try:
                idx = all_strikes.index(k_short)
                idx_long = max(0, idx - 1) if right == "P" else min(len(all_strikes) - 1, idx + 1)
                k_long = float(all_strikes[idx_long])
            except Exception:
                continue

        # Prefer DF mids (offline/CI); fallback to broker pricing
        mid_short = _mid_from_df(calls if right == "C" else puts, k_short)
        mid_long = _mid_from_df(calls if right == "C" else puts, k_long)
        if mid_short is None or mid_long is None:
            q_short = _price_leg(symbol, expiry, k_short, right)
            q_long = _price_leg(symbol, expiry, k_long, right)
            mid_short = q_short.get("mid") or 0.0
            mid_long = q_long.get("mid") or 0.0
        credit = max(0.0, float(mid_short) - float(mid_long))
        width = abs(k_long - k_short)
        if width <= 0:
            continue
        max_loss = max(0.0, width - credit)
        pop = max(0.0, 1.0 - float(abs(short_row["delta"])) if not math.isnan(short_row["delta"]) else 0.0)
        breakeven = (k_short - credit) if right == "P" else (k_short + credit)

        cand = {
                "profile": p.name,
                "underlying": symbol,
                "expiry": expiry,
                "legs": [
                    {"secType": "OPT", "right": right, "strike": k_short, "qty": -1, "expiry": expiry},
                    {"secType": "OPT", "right": right, "strike": k_long, "qty": 1, "expiry": expiry},
                ],
                "credit": credit,
                "width": width,
                "max_loss": max_loss,
                "pop_proxy": pop,
                "breakevens": [breakeven],
                "liquidity": {
                    "spread_pct_short": float(short_row.get("spread_pct", float("nan"))),
                    "oi_short": int(short_row.get("openInterest", 0)),
                    "vol_short": int(short_row.get("volume", 0)),
                },
                "em": {
                    "value": em,
                    "distance_to_short": (spot - k_short) if right == "P" else (k_short - spot),
                },
                "rationale": f"target Δ≈{p.target_delta:.2f}, width≈{p.width:g}",
            }
        # Suggested qty based on risk budget if provided
        if risk_budget_pct is not None:
            nlq = netliq if netliq is not None else _ib_net_liq()
            try:
                budget = float(risk_budget_pct) * float(nlq)
            except Exception:
                budget = 0.0
            if budget and max_loss > 0:
                import math as _math
                cand["suggested_qty"] = max(1, int(_math.floor(budget / max_loss)))
                cand["risk_budget"] = budget
                cand["risk_budget_pct"] = risk_budget_pct
        results.append(cand)

    return results[:3]


def suggest_debit_vertical(
    symbol: str,
    expiry: str,
    side: str,  # 'bull_call' or 'bear_put'
    profile: str | None = None,
    rules: LiquidityRules | None = None,
    *,
    df_calls: Optional[pd.DataFrame] = None,
    df_puts: Optional[pd.DataFrame] = None,
    spot_override: Optional[float] = None,
    avoid_earnings: bool = True,
    earnings_window_days: int = 7,
) -> List[Dict[str, Any]]:
    """Suggest debit verticals targeting long-leg delta 0.40–0.50.

    Chooses widths from {2.5, 5, 10} to aim for debit ~25–35% of width.
    """
    profs = [
        Profile("balanced", 0.45, 5.0),
        Profile("conservative", 0.40, 5.0),
        Profile("aggressive", 0.50, 5.0),
    ]
    if profile:
        name = profile.lower()
        profs.sort(key=lambda p: 0 if p.name.startswith(name) else 1)
    rules = rules or LiquidityRules()
    if df_calls is None or df_puts is None or spot_override is None:
        calls, puts, spot, expiry_resolved = _yf_chain(symbol, expiry)
    else:
        calls, puts, spot, expiry_resolved = df_calls.copy(), df_puts.copy(), float(spot_override), expiry
    expiry = expiry_resolved
    if avoid_earnings and _earnings_near(symbol, expiry, earnings_window_days):
        return []

    dte = _compute_t_days(expiry)
    calls = _add_delta(calls, spot, dte, "C")
    puts = _add_delta(puts, spot, dte, "P")
    calls = _filter_liquidity(calls, rules)
    puts = _filter_liquidity(puts, rules)

    results: List[Dict[str, Any]] = []
    widths = [2.5, 5.0, 10.0]
    if side == "bull_call":
        df = calls.dropna(subset=["delta"]).copy()
        df["delta_abs"] = df["delta"].abs()
        right = "C"
        width_sign = 1  # long lower, short higher
    elif side == "bear_put":
        df = puts.dropna(subset=["delta"]).copy()
        df["delta_abs"] = df["delta"].abs()
        right = "P"
        width_sign = -1  # long higher, short lower
    else:
        return []

    all_strikes = sorted(df["strike"].astype(float).unique().tolist())

    for p in profs:
        df_sorted = df.iloc[(df["delta_abs"] - p.target_delta).abs().argsort()]
        if df_sorted.empty:
            continue
        long_row = df_sorted.iloc[0]
        k_long = float(long_row["strike"])
        best = None
        for w in widths:
            k_short_target = k_long + width_sign * w
            k_short = _nearest_strike(all_strikes, k_short_target)
            if k_short == k_long:
                continue
            # mids
            mid_long = _mid_from_df(calls if right == "C" else puts, k_long)
            mid_short = _mid_from_df(calls if right == "C" else puts, k_short)
            if mid_long is None or mid_short is None:
                ql = _price_leg(symbol, expiry, k_long, right)
                qs = _price_leg(symbol, expiry, k_short, right)
                mid_long = ql.get("mid") or 0.0
                mid_short = qs.get("mid") or 0.0
            debit = max(0.0, float(mid_long) - float(mid_short))
            width = abs(k_short - k_long)
            if width <= 0:
                continue
            frac = debit / width if width else 1.0
            score = abs(frac - 0.30)
            cand = {
                "profile": p.name,
                "underlying": symbol,
                "expiry": expiry,
                "legs": [
                    {"secType": "OPT", "right": right, "strike": k_long, "qty": 1, "expiry": expiry},
                    {"secType": "OPT", "right": right, "strike": k_short, "qty": -1, "expiry": expiry},
                ],
                "debit": debit,
                "width": width,
                "debit_frac": frac,
                "breakeven": (k_long + debit) if right == "C" else (k_long - debit),
                "rationale": f"long Δ≈{p.target_delta:.2f}, width≈{w:g}, debit≈{frac:.2f} of width",
            }
            best = min([best, (score, cand)], key=lambda t: (t is None, t[0])) if best else (score, cand)
        if best:
            results.append(best[1])
    return results[:3]


def suggest_iron_condor(
    symbol: str,
    expiry: str,
    profile: str | None = None,
    rules: LiquidityRules | None = None,
    *,
    df_calls: Optional[pd.DataFrame] = None,
    df_puts: Optional[pd.DataFrame] = None,
    spot_override: Optional[float] = None,
    avoid_earnings: bool = True,
    earnings_window_days: int = 7,
    risk_budget_pct: Optional[float] = None,
    netliq: Optional[float] = None,
) -> List[Dict[str, Any]]:
    profs = [
        _pick_profile("conservative"),
        _pick_profile("balanced"),
        _pick_profile("aggressive"),
    ]
    if profile:
        sel = _pick_profile(profile)
        profs = [sel] + [p for p in profs if p.name != sel.name]
    rules = rules or LiquidityRules()
    if df_calls is None or df_puts is None or spot_override is None:
        calls, puts, spot, expiry_resolved = _yf_chain(symbol, expiry)
    else:
        calls, puts, spot, expiry_resolved = df_calls.copy(), df_puts.copy(), float(spot_override), expiry
    expiry = expiry_resolved
    if avoid_earnings and _earnings_near(symbol, expiry, earnings_window_days):
        return []
    dte = _compute_t_days(expiry)
    calls = _add_delta(calls, spot, dte, "C")
    puts = _add_delta(puts, spot, dte, "P")
    calls = _filter_liquidity(calls, rules)
    puts = _filter_liquidity(puts, rules)
    results: List[Dict[str, Any]] = []
    for p in profs:
        dfc = calls.dropna(subset=["delta"]).copy()
        dfp = puts.dropna(subset=["delta"]).copy()
        dfc["delta_abs"], dfp["delta_abs"] = dfc["delta"].abs(), dfp["delta"].abs()
        if dfc.empty or dfp.empty:
            continue
        short_call = dfc.iloc[(dfc["delta_abs"] - p.target_delta).abs().argsort()].iloc[0]
        short_put = dfp.iloc[(dfp["delta_abs"] - p.target_delta).abs().argsort()].iloc[0]
        kc_s = float(short_call["strike"])
        kp_s = float(short_put["strike"])
        wings = p.width
        kc_l = kc_s + wings
        kp_l = kp_s - wings
        mid_sc = _mid_from_df(calls, kc_s) or 0.0
        mid_sp = _mid_from_df(puts, kp_s) or 0.0
        mid_lc = _mid_from_df(calls, kc_l) or 0.0
        mid_lp = _mid_from_df(puts, kp_l) or 0.0
        credit = max(0.0, (mid_sc - mid_lc) + (mid_sp - mid_lp))
        width = max(abs(kc_l - kc_s), abs(kp_s - kp_l))
        max_loss = max(0.0, width - credit)
        cand = {
            "profile": p.name,
            "underlying": symbol,
            "expiry": expiry,
            "legs": [
                {"secType": "OPT", "right": "P", "strike": kp_s, "qty": -1, "expiry": expiry},
                {"secType": "OPT", "right": "P", "strike": kp_l, "qty": 1, "expiry": expiry},
                {"secType": "OPT", "right": "C", "strike": kc_s, "qty": -1, "expiry": expiry},
                {"secType": "OPT", "right": "C", "strike": kc_l, "qty": 1, "expiry": expiry},
            ],
            "credit": credit,
            "width": width,
            "max_loss": max_loss,
            "rationale": f"short Δ≈{p.target_delta:.2f} both sides, wings≈{wings:g}",
        }
        if risk_budget_pct is not None:
            nlq = netliq if netliq is not None else _ib_net_liq()
            try:
                budget = float(risk_budget_pct) * float(nlq)
            except Exception:
                budget = 0.0
            if budget and max_loss > 0:
                import math as _math
                cand["suggested_qty"] = max(1, int(_math.floor(budget / max_loss)))
                cand["risk_budget"] = budget
                cand["risk_budget_pct"] = risk_budget_pct
        results.append(cand)
    return results[:3]


def suggest_butterfly(
    symbol: str,
    expiry: str,
    right: str,  # 'C' or 'P'
    profile: str | None = None,
    rules: LiquidityRules | None = None,
    *,
    df_calls: Optional[pd.DataFrame] = None,
    df_puts: Optional[pd.DataFrame] = None,
    spot_override: Optional[float] = None,
    avoid_earnings: bool = True,
    earnings_window_days: int = 7,
) -> List[Dict[str, Any]]:
    """Suggest debit butterflies centred near ATM with widths {2.5, 5, 10}.

    Returns up to 3 profile-based candidates (conservative/balanced/aggressive)
    using the requested right (C or P).
    """
    widths = {
        "conservative": 10.0,
        "balanced": 5.0,
        "aggressive": 2.5,
    }
    profs = ["balanced", "conservative", "aggressive"]
    if profile:
        p = profile.lower()
        profs = [p] + [x for x in profs if x != p]
    rules = rules or LiquidityRules()

    if df_calls is None or df_puts is None or spot_override is None:
        calls, puts, spot, expiry_resolved = _yf_chain(symbol, expiry)
    else:
        calls, puts, spot, expiry_resolved = df_calls.copy(), df_puts.copy(), float(spot_override), expiry
    expiry = expiry_resolved
    if avoid_earnings and _earnings_near(symbol, expiry, earnings_window_days):
        return []
    dte = _compute_t_days(expiry)
    calls = _add_delta(calls, spot, dte, "C")
    puts = _add_delta(puts, spot, dte, "P")
    calls = _filter_liquidity(calls, rules)
    puts = _filter_liquidity(puts, rules)
    df = calls if right == "C" else puts
    if df.empty:
        return []
    # Choose center near ATM (strike nearest spot)
    strikes = sorted(df["strike"].astype(float).unique().tolist())
    if not strikes:
        return []
    center = _nearest_strike(strikes, float(spot))
    results: List[Dict[str, Any]] = []
    for name in profs:
        w = widths.get(name, 5.0)
        low = _nearest_strike(strikes, center - w)
        high = _nearest_strike(strikes, center + w)
        if low >= center or high <= center:
            continue
        mid_low = _mid_from_df(df, low) or 0.0
        mid_mid = _mid_from_df(df, center) or 0.0
        mid_high = _mid_from_df(df, high) or 0.0
        # Debit butterfly: long wings +1, short center -2
        debit = max(0.0, float(mid_low + mid_high - 2 * mid_mid))
        results.append({
            "profile": name,
            "underlying": symbol,
            "expiry": expiry,
            "legs": [
                {"secType": "OPT", "right": right, "strike": low, "qty": 1, "expiry": expiry},
                {"secType": "OPT", "right": right, "strike": center, "qty": -2, "expiry": expiry},
                {"secType": "OPT", "right": right, "strike": high, "qty": 1, "expiry": expiry},
            ],
            "debit": debit,
            "width": float(high - low) / 2.0,
            "debit_frac": (debit / (high - low)) if (high - low) else 1.0,
            "rationale": f"ATM center≈{center:g}, wings≈{w:g}",
        })
    return results[:3]


def suggest_calendar(
    symbol: str,
    expiry_far: str,
    right: str,
    profile: str | None = None,
    rules: LiquidityRules | None = None,
    *,
    near_dte: int = 30,
    far_dte: int = 60,
    df_calls_near: Optional[pd.DataFrame] = None,
    df_puts_near: Optional[pd.DataFrame] = None,
    df_calls_far: Optional[pd.DataFrame] = None,
    df_puts_far: Optional[pd.DataFrame] = None,
    spot_override: Optional[float] = None,
    avoid_earnings: bool = True,
    earnings_window_days: int = 7,
    avoid_inverted_term: bool = False,
    strike_offset: int = 0,
) -> List[Dict[str, Any]]:
    """Suggest a simple ATM calendar (short near, long far) with ATM bias.

    - Chooses ATM strike via spot to nearest strike
    - Near/far expiries default to ~30/60 DTE; snaps to listed expiries
    - Optionally checks term structure (avoid inverted near IV > far IV)
    """
    from datetime import date, timedelta

    rules = rules or LiquidityRules()
    # Resolve expiries via Yahoo list
    far_resolved, exps = _nearest_yf_expiry(symbol, expiry_far)
    # Derive near target by subtracting ~30 days, then snap
    try:
        far_dt = pd.to_datetime(far_resolved).date()
    except Exception:
        far_dt = date.today() + timedelta(days=far_dte)
    near_target = (far_dt - timedelta(days=far_dte - near_dte)).isoformat()
    near_resolved, _ = _nearest_yf_expiry(symbol, near_target)

    # Load chains (or injected DFs)
    if df_calls_near is None or df_puts_near is None or df_calls_far is None or df_puts_far is None or spot_override is None:
        calls_far, puts_far, spot, far_resolved = _yf_chain(symbol, far_resolved)
        calls_near, puts_near, _, near_resolved = _yf_chain(symbol, near_resolved)
    else:
        calls_near, puts_near = df_calls_near.copy(), df_puts_near.copy()
        calls_far, puts_far = df_calls_far.copy(), df_puts_far.copy()
        spot = float(spot_override)
    if avoid_earnings and (_earnings_near(symbol, near_resolved, earnings_window_days) or _earnings_near(symbol, far_resolved, earnings_window_days)):
        return []

    dte_near = _compute_t_days(near_resolved)
    dte_far = _compute_t_days(far_resolved)
    calls_near = _add_delta(calls_near, spot, dte_near, "C")
    puts_near = _add_delta(puts_near, spot, dte_near, "P")
    calls_far = _add_delta(calls_far, spot, dte_far, "C")
    puts_far = _add_delta(puts_far, spot, dte_far, "P")
    calls_near = _filter_liquidity(calls_near, rules)
    puts_near = _filter_liquidity(puts_near, rules)
    calls_far = _filter_liquidity(calls_far, rules)
    puts_far = _filter_liquidity(puts_far, rules)

    df_near = calls_near if right == "C" else puts_near
    df_far = calls_far if right == "C" else puts_far
    if df_near.empty or df_far.empty:
        return []
    strikes = sorted(set(df_near["strike"].astype(float)).intersection(set(df_far["strike"].astype(float))))
    if not strikes:
        return []
    center = _nearest_strike(strikes, float(spot))
    # Apply diagonal offset: calls move up, puts move down
    try:
        idx = strikes.index(center)
    except ValueError:
        idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - center))
    if strike_offset and isinstance(strike_offset, int):
        if right == "C":
            idx_far = min(len(strikes) - 1, idx + max(0, strike_offset))
        else:
            idx_far = max(0, idx - max(0, strike_offset))
    else:
        idx_far = idx
    far_strike = strikes[idx_far]
    mid_short = _mid_from_df(df_near, center) or 0.0
    mid_long = _mid_from_df(df_far, far_strike) or 0.0
    debit = max(0.0, float(mid_long) - float(mid_short))
    # Term structure check (median IVs)
    near_iv = float(df_near.get("impliedVolatility").median() or 0.0)
    far_iv = float(df_far.get("impliedVolatility").median() or 0.0)
    inverted = near_iv > far_iv + 1e-6
    if avoid_inverted_term and inverted:
        return []
    return [{
        "profile": (profile or "balanced"),
        "underlying": symbol,
        "expiry": far_resolved,
        "legs": [
            {"secType": "OPT", "right": right, "strike": center, "qty": -1, "expiry": near_resolved},
            {"secType": "OPT", "right": right, "strike": far_strike, "qty": 1, "expiry": far_resolved},
        ],
        "debit": debit,
        "near": near_resolved,
        "far": far_resolved,
        "strike_near": center,
        "strike_far": far_strike,
        "term_structure": {"near_iv": near_iv, "far_iv": far_iv, "inverted": inverted},
        "rationale": f"ATM calendar near≈{dte_near}D, far≈{dte_far}D",
    }]
