"""Market Stress Barometer (MSB) analytics."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

ColorLiteral = Literal["green", "yellow", "orange", "red"]
CalendarMode = Literal["observed_union", "legacy_weekdays"]
RuleBSource = Literal["raw", "winsor"]

_LOG = logging.getLogger("psd.analytics.msb")


@dataclass(slots=True)
class MsbReading:
    """Typed container for MSB readings."""

    date: date
    hy_oas: float
    vx1: float
    vx2: float
    z_hy: float
    term_ratio: float
    cal_spread_pct: float
    cal_spread_abs: float
    saturated: bool
    hy_score: int
    vix_score: int
    msb: int
    color: ColorLiteral
    triggers: list[str]
    winsor_clipped_n: int
    cooldown_until: date | None


@dataclass(slots=True)
class MSBConfig:
    """Configuration knobs for MSB analytics."""

    calendar_mode: CalendarMode = "observed_union"
    ffill_hy_days: int = 2
    ffill_vix_days: int = 2
    ffill_spx_ret_days: int = 0
    rule_b_source: RuleBSource = "raw"
    rule_b_delta_clip_abs: float | None = 3.00
    hy_targets: tuple[float, float, float] = (25.0, 40.0, 50.0)
    require_fresh_streak_after_cooldown: bool = False

    @classmethod
    def legacy(cls) -> MSBConfig:
        """Return a config that mirrors the pre-2026 MSB defaults."""
        return cls(
            calendar_mode="legacy_weekdays",
            ffill_spx_ret_days=2,
            rule_b_source="winsor",
            hy_targets=(25.0, 80.0, 95.0),
        )


def _ensure_series(name: str, raw: Iterable[float] | pd.Series) -> pd.Series:
    if isinstance(raw, pd.Series):
        series = raw.copy()
    else:
        series = pd.Series(list(raw), name=name)
    if series.empty:
        raise ValueError(f"{name} series is empty")
    idx = pd.to_datetime(series.index)
    series = pd.Series(series.astype(float).to_numpy(), index=idx, name=name)
    series.sort_index(inplace=True)
    return series


def _normalize_series(name: str, raw: Iterable[float] | pd.Series) -> pd.Series:
    series = _ensure_series(name, raw)
    series.index = pd.to_datetime(series.index).normalize()
    series = series[~series.index.duplicated(keep="last")]
    series.sort_index(inplace=True)
    return series


def _build_calendar_index(
    hy_series: pd.Series,
    vx1_series: pd.Series,
    vx2_series: pd.Series,
    spx_series: pd.Series | None,
    config: MSBConfig,
) -> pd.DatetimeIndex:
    if config.calendar_mode == "legacy_weekdays":
        start = min(
            hy_series.index.min(),
            vx1_series.index.min(),
            vx2_series.index.min(),
        )
        end = max(
            hy_series.index.max(),
            vx1_series.index.max(),
            vx2_series.index.max(),
        )
        if spx_series is not None and not spx_series.empty:
            start = min(start, spx_series.index.min())
            end = max(end, spx_series.index.max())
        return pd.bdate_range(start=start, end=end)

    indices = [hy_series.index, vx1_series.index, vx2_series.index]
    if spx_series is not None and not spx_series.empty:
        indices.append(spx_series.index)
    union_idx = indices[0]
    for extra in indices[1:]:
        union_idx = union_idx.union(extra)
    return union_idx.sort_values()


def _apply_ffill(series: pd.Series, limit: int) -> pd.Series:
    if limit <= 0:
        return series
    return series.ffill(limit=limit)


def _clip_rule_b_delta(
    series: pd.Series,
    abs_limit: float | None,
    label: str,
) -> pd.Series:
    if abs_limit is None:
        return series
    limit = float(abs_limit)
    if limit <= 0:
        return series
    mask = series.abs() > limit
    if mask.any():
        _LOG.warning(
            "MSB Rule B %s delta clipped for %s points (limit=%.2f)",
            label,
            int(mask.sum()),
            limit,
        )
    return series.clip(lower=-limit, upper=limit)


def _rolling_winsorize(
    series: pd.Series,
    window: int,
    fallback: int,
    lower_q: float,
    upper_q: float,
) -> tuple[pd.Series, pd.Series]:
    min_periods = max(2, min(window, fallback))
    primary_low = series.rolling(window=window, min_periods=min_periods).quantile(
        lower_q
    )
    primary_high = series.rolling(window=window, min_periods=min_periods).quantile(
        upper_q
    )

    fb_min_periods = max(2, min(fallback, window))
    fb_low = series.rolling(window=fallback, min_periods=fb_min_periods).quantile(
        lower_q
    )
    fb_high = series.rolling(window=fallback, min_periods=fb_min_periods).quantile(
        upper_q
    )

    low = primary_low.where(primary_low.notna(), fb_low)
    high = primary_high.where(primary_high.notna(), fb_high)
    clipped = series
    mask = low.notna() & high.notna()
    clipped = clipped.where(~mask, series.clip(lower=low, upper=high))
    clipped_diff = ((series - clipped).abs() > np.finfo(float).eps).astype(
        int
    ) * mask.astype(int)
    return clipped, clipped_diff


def _z_score(series: pd.Series, window: int, fallback: int) -> pd.Series:
    min_periods = max(2, min(window, fallback))
    rolling_mean = (
        series.rolling(window=window, min_periods=min_periods).mean().astype(float)
    )
    rolling_std = series.rolling(window=window, min_periods=min_periods).std(ddof=0)

    fb_mean = series.rolling(window=fallback, min_periods=2).mean()
    fb_std = series.rolling(window=fallback, min_periods=2).std(ddof=0)

    z_primary = (series - rolling_mean) / rolling_std
    z_fallback = (series - fb_mean) / fb_std

    z = z_primary.where(rolling_std > 0, z_fallback)
    z = z.where(z.replace([np.inf, -np.inf], np.nan).notna(), z_fallback)
    return z.replace([np.inf, -np.inf], np.nan)


def _piecewise_score(
    value: float,
    anchors: tuple[float, float, float],
    targets: tuple[float, float, float],
) -> float:
    a0, a1, a2 = anchors
    t0, t1, t2 = targets
    if not np.isfinite(value) or not all(np.isfinite(x) for x in anchors):
        return np.nan
    if a1 == a0 or a2 == a1:
        return np.nan
    if value <= a0:
        slope = (t1 - t0) / (a1 - a0)
        return t0 + (value - a0) * slope
    if value <= a1:
        slope = (t1 - t0) / (a1 - a0)
        return t0 + (value - a0) * slope
    if value <= a2:
        slope = (t2 - t1) / (a2 - a1)
        return t1 + (value - a1) * slope
    slope = (t2 - t1) / (a2 - a1)
    return t2 + (value - a2) * slope


def _calibrated_score(
    series: pd.Series,
    window: int,
    fallback: int,
    targets: tuple[float, float, float],
) -> pd.Series:
    q50 = series.rolling(window=window, min_periods=fallback).quantile(0.5)
    q90 = series.rolling(window=window, min_periods=fallback).quantile(0.9)
    q99 = series.rolling(window=window, min_periods=fallback).quantile(0.99)

    q50_fb = series.rolling(window=fallback, min_periods=fallback).quantile(0.5)
    q90_fb = series.rolling(window=fallback, min_periods=fallback).quantile(0.9)
    q99_fb = series.rolling(window=fallback, min_periods=fallback).quantile(0.99)

    q50 = q50.where(q50.notna(), q50_fb)
    q90 = q90.where(q90.notna(), q90_fb)
    q99 = q99.where(q99.notna(), q99_fb)

    scores: list[float] = []
    for val, a0, a1, a2 in zip(
        series.to_numpy(), q50.to_numpy(), q90.to_numpy(), q99.to_numpy(), strict=False
    ):
        score = _piecewise_score(val, (a0, a1, a2), targets)
        scores.append(score)
    return pd.Series(scores, index=series.index, name="calibrated_score")


def compute_msb(
    hy: pd.Series,
    vx1: pd.Series,
    vx2: pd.Series,
    window: int = 252,
    fallback: int = 63,
    lq: float = 0.01,
    uq: float = 0.99,
    spx_ret: pd.Series | None = None,
    config: MSBConfig | None = None,
) -> pd.DataFrame:
    """Compute MSB analytics with guardrails."""
    cfg = config or MSBConfig()
    hy_series = _normalize_series("hy", hy)
    vx1_series = _normalize_series("vx1", vx1)
    vx2_series = _normalize_series("vx2", vx2)
    spx_series_raw = _normalize_series("spx", spx_ret) if spx_ret is not None else None

    idx = _build_calendar_index(hy_series, vx1_series, vx2_series, spx_series_raw, cfg)

    hy_aligned = _apply_ffill(hy_series.reindex(idx), cfg.ffill_hy_days)
    vx1_aligned = _apply_ffill(vx1_series.reindex(idx), cfg.ffill_vix_days)
    vx2_aligned = _apply_ffill(vx2_series.reindex(idx), cfg.ffill_vix_days)

    df = pd.concat([hy_aligned, vx1_aligned, vx2_aligned], axis=1)
    df.columns = ["hy", "vx1", "vx2"]
    df = df.dropna(how="all")

    winsorized = {}
    clipped_counts = []
    for col in df.columns:
        clipped, diff = _rolling_winsorize(df[col], window, fallback, lq, uq)
        winsorized[col] = clipped
        clipped_counts.append(diff)
    w_df = pd.DataFrame(winsorized)
    winsor_matrix = pd.concat(clipped_counts, axis=1).fillna(0).astype(int)
    winsor_matrix.columns = [f"{col}_clip" for col in df.columns]
    winsor_counts = winsor_matrix.sum(axis=1)

    z_hy = _z_score(w_df["hy"], window, fallback)

    vx2_safe = w_df["vx2"].replace(0.0, np.nan)
    term_ratio = (w_df["vx1"] / vx2_safe) - 1.0
    cal_spread_abs = w_df["vx1"] - w_df["vx2"]
    cal_spread_pct = cal_spread_abs / vx2_safe

    saturated = (
        (w_df["vx1"] >= 40)
        & (cal_spread_abs >= 3)
        & (term_ratio.between(-0.05, 0.05, inclusive="both"))
    )

    hy_calibrated = _calibrated_score(
        w_df["hy"], window, fallback, targets=cfg.hy_targets
    )
    hy_fallback = 12.0 * z_hy + 25.0
    hy_score = hy_calibrated.where(hy_calibrated.notna(), hy_fallback)
    hy_score = hy_score.fillna(hy_fallback).fillna(25.0)
    hy_score = hy_score.clip(lower=0, upper=50).round().astype(int)

    pct_calibrated = _calibrated_score(
        cal_spread_pct.fillna(0.0), window, fallback, targets=(20.0, 40.0, 48.0)
    )
    abs_calibrated = _calibrated_score(
        cal_spread_abs.fillna(0.0), window, fallback, targets=(15.0, 35.0, 48.0)
    )
    pct_fallback = (cal_spread_pct.fillna(0.0) * 100.0).clip(lower=0.0, upper=50.0)
    abs_fallback = (cal_spread_abs.fillna(0.0) * 2.0).clip(lower=0.0, upper=50.0)
    pct_track = pct_calibrated.where(pct_calibrated.notna(), pct_fallback)
    abs_track = abs_calibrated.where(abs_calibrated.notna(), abs_fallback)
    vix_score = pd.concat([pct_track, abs_track], axis=1).max(axis=1)
    vix_score = vix_score.fillna(0.0)
    vix_score = vix_score + saturated.astype(int) * 3.0
    vix_score = vix_score.clip(lower=0, upper=50).round().astype(int)

    msb = (hy_score + vix_score).clip(0, 100).astype(int)

    color = pd.Series(
        np.select(
            [
                msb < 30,
                (msb >= 30) & (msb < 50),
                (msb >= 50) & (msb < 70),
            ],
            ["green", "yellow", "orange"],
            default="red",
        ),
        index=msb.index,
        name="color",
    )

    if spx_series_raw is not None:
        spx_series = spx_series_raw.reindex(w_df.index)
        spx_series = _apply_ffill(spx_series, cfg.ffill_spx_ret_days)
    else:
        spx_series = pd.Series(index=w_df.index, dtype=float)

    triggers: list[list[str]] = []
    cooldown_until: list[pd.Timestamp | pd.NaT] = []
    cooldown_active_until: pd.Timestamp | None = None

    msb_ge_60 = msb >= 60
    hy_delta_source = w_df["hy"] if cfg.rule_b_source == "winsor" else df["hy"]
    hy_delta = _clip_rule_b_delta(
        hy_delta_source.diff(), cfg.rule_b_delta_clip_abs, "d1"
    )
    hy_delta5 = _clip_rule_b_delta(
        hy_delta_source.diff(5), cfg.rule_b_delta_clip_abs, "d5"
    )
    post_cooldown_streak = 0

    for idx in w_df.index:
        trigger_flags: list[str] = []
        vx1_gt_vx2 = w_df.at[idx, "vx1"] > w_df.at[idx, "vx2"]
        spx_val = spx_series.at[idx] if idx in spx_series.index else np.nan
        if vx1_gt_vx2 and np.isfinite(spx_val) and spx_val < 0:
            trigger_flags.append("A")

        d1 = hy_delta.get(idx, np.nan)
        d5 = hy_delta5.get(idx, np.nan)
        if (np.isfinite(d1) and d1 >= 0.25) or (np.isfinite(d5) and d5 >= 0.60):
            trigger_flags.append("B")

        current_cooldown = cooldown_active_until
        trigger_c = False
        in_cooldown = current_cooldown is not None and idx <= current_cooldown
        if msb_ge_60.at[idx]:
            if cfg.require_fresh_streak_after_cooldown:
                if in_cooldown:
                    post_cooldown_streak = 0
                else:
                    post_cooldown_streak += 1
            prev_idx = w_df.index.get_loc(idx)
            if cfg.require_fresh_streak_after_cooldown:
                if post_cooldown_streak >= 3 and not in_cooldown:
                    trigger_c = True
            elif prev_idx >= 2:
                window_slice = msb_ge_60.iloc[prev_idx - 2 : prev_idx + 1]
                if window_slice.all() and not in_cooldown:
                    trigger_c = True
        else:
            post_cooldown_streak = 0

        if trigger_c:
            cooldown_active_until = (idx + BDay(5)).normalize()
        if trigger_c:
            trigger_flags.append("C")
            cooldown_until.append(cooldown_active_until)
        else:
            cooldown_until.append(
                cooldown_active_until
                if cooldown_active_until and idx <= cooldown_active_until
                else pd.NaT
            )

        triggers.append(trigger_flags)

    cooldown_series = pd.Series(cooldown_until, index=w_df.index, name="cooldown_until")

    msb_df = pd.DataFrame(
        {
            "hy": w_df["hy"],
            "vx1": w_df["vx1"],
            "vx2": w_df["vx2"],
            "z_hy": z_hy,
            "term_ratio": term_ratio,
            "cal_spread_pct": cal_spread_pct,
            "cal_spread_abs": cal_spread_abs,
            "saturated": saturated.astype(bool),
            "hy_score": hy_score,
            "vix_score": vix_score,
            "msb": msb,
            "color": color,
            "triggers": triggers,
            "winsor_clipped_n": winsor_counts.astype(int),
            "cooldown_until": cooldown_series,
        }
    )
    msb_df.index.name = "date"
    return msb_df


__all__ = ["MSBConfig", "MsbReading", "compute_msb"]
