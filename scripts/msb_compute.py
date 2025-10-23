"""CLI to compute Market Stress Barometer readings."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from psd.analytics.msb import compute_msb

_JSON_SEPARATORS = (",", ":")


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
            anomalies.append({"date": date_iso, "kind": "nan_detected", "columns": na_cols})
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
    parser.add_argument("--vx1-csv", required=True, type=Path, help="VIX front CSV path")
    parser.add_argument("--vx2-csv", required=True, type=Path, help="VIX second CSV path")
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
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    hy_series = _load_series(args.hy_csv)
    vx1_series = _load_series(args.vx1_csv)
    vx2_series = _load_series(args.vx2_csv)
    spx_series = _load_series(args.spx_csv) if args.spx_csv else None

    lower_q, upper_q = args.winsor
    df = compute_msb(
        hy=hy_series,
        vx1=vx1_series,
        vx2=vx2_series,
        window=args.window,
        fallback=args.fallback,
        lq=lower_q,
        uq=upper_q,
        spx_ret=spx_series,
    )

    _ensure_parent(args.out)
    _write_csv(df, args.out)
    if args.anomalies:
        anomalies = _collect_anomalies(df)
        _append_anomalies(anomalies, args.anomalies)


if __name__ == "__main__":
    main()
