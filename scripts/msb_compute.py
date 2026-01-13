"""CLI to compute Market Stress Barometer readings."""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from psd.analytics.msb import MSBConfig, compute_msb
from psd.datasources import resolve_msb_source
from psd.datasources.fred import refresh_hy_csv

_JSON_SEPARATORS = (",", ":")
logger = logging.getLogger("psd.scripts.msb_compute")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _load_series(csv_path: Path) -> pd.Series:
    frame = pd.read_csv(csv_path, parse_dates=["date"])
    if "value" not in frame.columns:
        raise ValueError(f"{csv_path} missing 'value' column")
    series = frame.set_index("date")["value"].astype(float).sort_index()
    series.index = pd.to_datetime(series.index)
    return series


def _write_csv(df: pd.DataFrame, output_path: Path) -> None:
    payload = df.copy()
    payload = payload.reset_index()
    payload["date"] = payload["date"].dt.date.apply(lambda x: x.isoformat())
    payload["triggers"] = payload["triggers"].apply(
        lambda items: json.dumps(list(items), separators=_JSON_SEPARATORS)
    )

    def _fmt_cooldown(value: object) -> str:
        if pd.isna(value):
            return ""
        ts = pd.Timestamp(value)
        return ts.date().isoformat()

    payload["cooldown_until"] = payload["cooldown_until"].apply(_fmt_cooldown)
    payload.to_csv(output_path, index=False)


def _collect_anomalies(df: pd.DataFrame) -> list[dict[str, object]]:
    anomalies: list[dict[str, object]] = []
    for idx, row in df.iterrows():
        date_iso = pd.Timestamp(idx).date().isoformat()
        winsor_count = int(row.get("winsor_clipped_n", 0))
        if winsor_count > 0:
            anomalies.append(
                {"date": date_iso, "kind": "winsor_clip", "count": winsor_count}
            )
        na_cols = []
        for col, value in row.items():
            if col == "triggers":
                continue
            try:
                if pd.isna(value):
                    na_cols.append(col)
            except TypeError:
                continue
        if na_cols:
            anomalies.append(
                {"date": date_iso, "kind": "nan_detected", "columns": na_cols}
            )
    return anomalies


def _append_anomalies(anomalies: Iterable[dict[str, object]], path: Path) -> None:
    if not anomalies:
        return
    _ensure_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        for entry in anomalies:
            handle.write(json.dumps(entry, separators=_JSON_SEPARATORS))
            handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute MSB readings.")
    parser.add_argument("--hy-csv", required=True, type=Path, help="HY OAS CSV path")
    parser.add_argument(
        "--vx1-csv", required=True, type=Path, help="VIX front CSV path"
    )
    parser.add_argument(
        "--vx2-csv", required=True, type=Path, help="VIX second CSV path"
    )
    parser.add_argument("--spx-csv", type=Path, help="Optional SPX return CSV path")
    parser.add_argument("--out", required=True, type=Path, help="Output CSV path")
    parser.add_argument(
        "--anomalies", type=Path, help="Optional anomaly log (JSONL, append mode)"
    )
    parser.add_argument("--window", type=int, default=252, help="Primary window size")
    parser.add_argument("--fallback", type=int, default=63, help="Fallback window size")
    parser.add_argument(
        "--winsor",
        nargs=2,
        type=float,
        default=(0.01, 0.99),
        metavar=("LOWER_Q", "UPPER_Q"),
        help="Winsorization quantile bounds",
    )
    parser.add_argument(
        "--calendar-mode",
        choices=["observed_union", "legacy_weekdays"],
        default="observed_union",
        help="Index construction mode for MSB",
    )
    parser.add_argument(
        "--rule-b-source",
        choices=["raw", "winsor"],
        default="raw",
        help="HY series source for Rule B deltas",
    )
    parser.add_argument(
        "--rule-b-delta-clip-abs",
        type=float,
        default=3.0,
        help="Absolute clip for Rule B deltas (HY points); <=0 disables",
    )
    parser.add_argument(
        "--ffill-spx-ret-days",
        type=int,
        default=0,
        help="Forward-fill window for SPX returns (0 disables)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    env = os.environ
    msb_source = resolve_msb_source(env)
    if msb_source == "fred":
        try:
            refreshed = refresh_hy_csv(args.hy_csv, env=env)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("FRED refresh skipped: %s", exc)
        else:
            if refreshed:
                logger.info("HY-OAS CSV refreshed from FRED: %s", args.hy_csv)

    hy_series = _load_series(args.hy_csv)
    vx1_series = _load_series(args.vx1_csv)
    vx2_series = _load_series(args.vx2_csv)
    spx_series = _load_series(args.spx_csv) if args.spx_csv else None

    lower_q, upper_q = args.winsor
    config = MSBConfig(
        calendar_mode=args.calendar_mode,
        rule_b_source=args.rule_b_source,
        rule_b_delta_clip_abs=args.rule_b_delta_clip_abs,
        ffill_spx_ret_days=args.ffill_spx_ret_days,
    )
    df = compute_msb(
        hy=hy_series,
        vx1=vx1_series,
        vx2=vx2_series,
        window=args.window,
        fallback=args.fallback,
        lq=lower_q,
        uq=upper_q,
        spx_ret=spx_series,
        config=config,
    )

    _ensure_parent(args.out)
    _write_csv(df, args.out)
    if args.anomalies:
        anomalies = _collect_anomalies(df)
        _append_anomalies(anomalies, args.anomalies)


if __name__ == "__main__":
    main()
