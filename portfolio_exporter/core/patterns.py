from __future__ import annotations

from typing import Dict, List, Any, Optional


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _vwap(bars: List[Dict[str, Any]]) -> Optional[float]:
    pv = 0.0
    tv = 0.0
    for b in bars:
        c = _safe_float(b.get("close"))
        v = _safe_float(b.get("volume"))
        pv += c * v
        tv += v
    if tv <= 0:
        return None
    return pv / tv


def _rvol(series: List[int | float]) -> float:
    if not series:
        return 0.0
    mean_vol = (sum(series) / max(1, len(series))) if series else 0.0
    last1 = sum(series[-1:])
    last5 = sum(series[-5:])
    if mean_vol <= 0:
        return 0.0
    r1 = last1 / mean_vol
    r5 = last5 / (mean_vol * min(5, len(series)))
    return max(0.0, float(r1)), max(0.0, float(r5))  # type: ignore[return-value]


def compute_patterns(bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute VWAP/ORB/HOD-LOD based intraday signals from 1-min bars.

    Input bars are expected in chronological order. Each bar is a dict with keys:
    close, high, low, volume (others ignored).
    """
    out: Dict[str, Any] = {
        "vwap": None,
        "rvol_1m": 0.0,
        "rvol_5m": 0.0,
        "orb_high": None,
        "orb_low": None,
        "above_vwap_now": "",
        "vwap_distance_pct": None,
        "pattern_signal": "",
    }
    if not bars:
        return out

    # RVOLs
    volumes = [_safe_float(b.get("volume", 0.0)) for b in bars]
    r1, r5 = _rvol(volumes)
    out["rvol_1m"] = r1
    out["rvol_5m"] = r5

    # VWAP
    vwap = _vwap(bars)
    out["vwap"] = vwap

    # ORB over first up to 5 bars
    orb_bars = bars[: min(5, len(bars))]
    if orb_bars:
        orb_hi = max(_safe_float(b.get("high", b.get("close", 0.0))) for b in orb_bars)
        orb_lo = min(_safe_float(b.get("low", b.get("close", 0.0))) for b in orb_bars)
        out["orb_high"] = orb_hi
        out["orb_low"] = orb_lo
    else:
        orb_hi = None

    # HOD/LOD so far
    hod = max(_safe_float(b.get("high", b.get("close", 0.0))) for b in bars)
    lod = min(_safe_float(b.get("low", b.get("close", 0.0))) for b in bars)

    last_close = _safe_float(bars[-1].get("close", 0.0))
    prev_close = _safe_float(bars[-2].get("close", last_close)) if len(bars) >= 2 else last_close

    # Above VWAP now + distance
    if isinstance(vwap, (int, float)) and vwap and vwap > 0:
        out["above_vwap_now"] = "Yes" if last_close >= float(vwap) else "No"
        out["vwap_distance_pct"] = abs((last_close - float(vwap)) / float(vwap))

    # Heuristics
    patt = ""
    eps = 0.001  # 0.1% tolerance for boundaries

    # ORB break / retest logic (highest priority)
    if isinstance(out.get("orb_high"), (int, float)) and out["orb_high"]:
        orb_high = float(out["orb_high"])  # type: ignore[assignment]
        broke_orb_before = any(_safe_float(b.get("close", 0.0)) > orb_high for b in bars[:-1])
        near_retest = abs(prev_close - orb_high) / orb_high <= 0.0015
        if last_close > orb_high and broke_orb_before and near_retest:
            patt = "ORB Retest"
        elif last_close > orb_high:
            patt = "ORB"

    # VWAP reclaim / reject (higher priority than HOD/LOD)
    if not patt and (isinstance(vwap, (int, float)) and vwap and vwap > 0):
        vwap_f = float(vwap)
        n = min(5, len(bars))
        first_n = bars[:n]
        below_cnt = sum(1 for b in first_n if _safe_float(b.get("close", 0.0)) < vwap_f * (1.0 - eps))
        mostly_below = below_cnt >= max(1, int(0.6 * n))
        rising_tail = len(bars) >= 3 and (_safe_float(bars[-3].get("close")) < _safe_float(bars[-2].get("close")) < last_close)
        if mostly_below and last_close >= vwap_f * (1.0 - eps) and rising_tail:
            patt = "VWAP Reclaim"
        elif prev_close >= vwap_f * (1.0 - eps) and last_close <= vwap_f * (1.0 + eps):
            patt = "VWAP Reject"

    # HOD reclaim / LOD break
    if not patt:
        # Recent HOD/LOD in a sliding window (exclude the last bar), to avoid early spikes dominating
        window = bars[max(0, len(bars) - 6) : -1] if len(bars) > 1 else []
        if not window:
            window = bars[:-1]
        prior_hod = max(_safe_float(b.get("high", b.get("close", 0.0))) for b in window) if window else hod
        prior_lod = min(_safe_float(b.get("low", b.get("close", 0.0))) for b in window) if window else lod
        if last_close > prior_hod * (1.0 + eps):
            patt = "HOD Reclaim"
        elif last_close < prior_lod * (1.0 - eps):
            patt = "LOD Break"

    # Fail if last close below VWAP after attempting above
    if not patt and isinstance(vwap, (int, float)) and vwap and prev_close > float(vwap) and last_close < float(vwap):
        patt = "Fail"

    out["pattern_signal"] = patt
    return out
