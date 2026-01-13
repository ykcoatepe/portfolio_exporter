# Market Stress Barometer (MSB)

## Overview
MSB is a composite risk/stress signal that combines HY credit spreads (HY-OAS)
with VIX term structure pressure to surface early stress regimes. It is used to
trigger hedge staging rules (A/B/C) rather than act as a standalone instrument.

## Inputs
- HY-OAS (daily close)
- VIX futures: VX1 (front) and VX2 (next)
- Optional SPX daily return (only needed for Rule A)

Data sources:
- IBKR (primary for VX1/VX2/SPX when `MSB_SOURCE=ibkr` and IB is available).
- FRED (HY-OAS refresh when `FRED_API_KEY` is set).
- Yahoo Finance fallback for VX1/VX2/SPX when IB is unavailable.
- Vendor refresh runs by default; set `PSD_MSB_AUTO_REFRESH=0` to disable refresh.

## Scoring (0–100)
- HY score (0–50): calibrated on rolling quantiles and clamped to [0, 50].
- VIX score (0–50): max of calibrated calendar % and abs tracks; +3 if saturated.
- MSB = HY score + VIX score (0–100).
- Colors: <30 green, <50 yellow, <70 orange, else red.

## Triggers
- Rule A (VIX backwardation probe): VX1 > VX2 AND SPX daily return < 0.
- Rule B (HY shock): HY-OAS +25 bps d/d OR +60 bps in 5 business days.
- Rule C (persistent stress): MSB >= 60 for 3 consecutive sessions, then cooldown
  for 5 business days.
  - API/SSE payloads expose these as `RULE_A_VIX_BACKWARDATION`,
    `RULE_B_HY_SHOCK`, and `RULE_C_MSB_60x3D`.

## Configuration knobs
All configuration lives in `psd.analytics.msb.MSBConfig`.

Defaults (safe for live use):
- calendar_mode = observed_union
- ffill_hy_days = 2
- ffill_vix_days = 2
- ffill_spx_ret_days = 0
- rule_b_source = raw
- rule_b_delta_clip_abs = 3.00
- hy_targets = (25.0, 40.0, 50.0)
- require_fresh_streak_after_cooldown = False

IBKR-specific knobs (used when `MSB_SOURCE=ibkr`):
- MSB_IBKR_VX_ROOT (default: VX)
- MSB_IBKR_VX_EXCHANGE (default: CFE)
- MSB_IBKR_VX_CURRENCY (default: USD)
- MSB_IBKR_SPX_SYMBOL (default: SPX)
- MSB_IBKR_SPX_EXCHANGE (default: CBOE)
- MSB_IBKR_SPX_CURRENCY (default: USD)
- MSB_IBKR_DURATION (overrides MSB_VENDOR_PERIOD; IB format like "5 Y")
- MSB_IBKR_BAR_SIZE (default: "1 day")
- MSB_IBKR_WHAT (default: "TRADES")
- MSB_IBKR_USE_RTH (default: true)

### Calendar rationale
By default, MSB uses the observed union of dates across inputs. This avoids
fabricating synthetic rows for holidays and prevents SPX returns from being
assumed on non-trading days.

To reproduce legacy behavior:
- Use `MSBConfig.legacy()` or set
  `calendar_mode=legacy_weekdays`, `ffill_spx_ret_days=2`,
  `rule_b_source=winsor`, and `hy_targets=(25.0, 80.0, 95.0)`.

### SPX returns not forward-filled
SPX returns are sparse by design. Forward-filling them can create false Rule A
signals on missing or non-trading days. Therefore the default is no fill.

## CLI
`scripts/msb_compute.py` accepts:
- `--calendar-mode observed_union|legacy_weekdays`
- `--rule-b-source raw|winsor`
- `--rule-b-delta-clip-abs <float>`
- `--ffill-spx-ret-days <int>`

`scripts/msb_refresh.py` refreshes vendor inputs (IBKR primary, YF fallback):
- `--vendor-dir <path>`
- `--json` (structured status output)

## Notes
- Rule B deltas use the raw aligned HY series by default with a guard
  against bad prints (absolute clip). This is logged if clipping occurs.
