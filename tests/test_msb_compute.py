import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from psd.analytics.msb import MSBConfig, compute_msb


def _baseline_series(
    start: str = "2024-01-02",
    periods: int = 80,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    idx = pd.bdate_range(start, periods=periods)
    steps = np.arange(periods, dtype=float)
    hy = pd.Series(4.0 + 0.01 * steps, index=idx)
    vx1 = pd.Series(18.0 + 0.02 * steps, index=idx)
    vx2 = pd.Series(20.0 + 0.015 * steps, index=idx)
    spx = pd.Series(0.0005, index=idx)
    return hy, vx1, vx2, spx


def test_compute_msb_columns_and_tail():
    hy, vx1, vx2, spx = _baseline_series()
    df = compute_msb(
        hy=hy, vx1=vx1, vx2=vx2, spx_ret=spx, window=30, fallback=10, lq=0.05, uq=0.95
    )
    expected_columns = {
        "hy",
        "vx1",
        "vx2",
        "z_hy",
        "term_ratio",
        "cal_spread_pct",
        "cal_spread_abs",
        "saturated",
        "hy_score",
        "vix_score",
        "msb",
        "color",
        "triggers",
        "winsor_clipped_n",
        "cooldown_until",
    }
    assert expected_columns.issubset(df.columns)
    tail = df.iloc[-1]
    numeric_cols = [
        "hy",
        "vx1",
        "vx2",
        "z_hy",
        "term_ratio",
        "cal_spread_pct",
        "cal_spread_abs",
        "hy_score",
        "vix_score",
        "msb",
        "winsor_clipped_n",
    ]
    assert tail[numeric_cols].notna().all()
    assert isinstance(tail["triggers"], list)
    assert tail["color"] in {"green", "yellow", "orange", "red"}


def test_color_mapping_matches_thresholds():
    hy, vx1, vx2, spx = _baseline_series()
    df = compute_msb(
        hy=hy, vx1=vx1, vx2=vx2, spx_ret=spx, window=30, fallback=10, lq=0.05, uq=0.95
    )
    expected = df["msb"].apply(
        lambda value: (
            "green"
            if value < 30
            else "yellow"
            if value < 50
            else "orange"
            if value < 70
            else "red"
        )
    )
    assert (df["color"] == expected).all()


def test_rule_c_sets_cooldown_after_three_high_days():
    periods = 120
    idx = pd.bdate_range("2024-01-02", periods=periods)
    hy = pd.Series(4.0, index=idx)
    hy.iloc[-30:] = 8.0
    vx1 = pd.Series(18.0, index=idx)
    vx1.iloc[-30:] = 45.0
    vx2 = pd.Series(20.0, index=idx)
    vx2.iloc[-30:] = 30.0
    spx = pd.Series(-0.002, index=idx)

    df = compute_msb(
        hy=hy, vx1=vx1, vx2=vx2, spx_ret=spx, window=40, fallback=15, lq=0.05, uq=0.95
    )
    triggered_rows = df[df["triggers"].apply(lambda flags: "C" in flags)]
    assert not triggered_rows.empty
    first_trigger = triggered_rows.iloc[0]
    assert pd.notna(first_trigger["cooldown_until"])
    cooldown_date = pd.Timestamp(first_trigger.name) + pd.tseries.offsets.BDay(5)
    assert pd.Timestamp(first_trigger["cooldown_until"]) == cooldown_date.normalize()
    subsequent = df.loc[first_trigger.name :]
    assert all(
        pd.isna(row["cooldown_until"]) or row["cooldown_until"] >= first_trigger["cooldown_until"]
        for _, row in subsequent.iterrows()
    )


def test_cli_logs_winsor_anomalies(tmp_path: Path):
    hy, vx1, vx2, spx = _baseline_series(periods=40)
    hy.iloc[-1] = hy.iloc[-2] * 8  # obvious outlier for winsorization

    def _write_csv(series: pd.Series, path: Path) -> None:
        frame = pd.DataFrame({"date": series.index, "value": series.values})
        frame.to_csv(path, index=False)

    hy_path = tmp_path / "hy.csv"
    vx1_path = tmp_path / "vx1.csv"
    vx2_path = tmp_path / "vx2.csv"
    spx_path = tmp_path / "spx.csv"
    _write_csv(hy, hy_path)
    _write_csv(vx1, vx1_path)
    _write_csv(vx2, vx2_path)
    _write_csv(spx, spx_path)

    out_path = tmp_path / "msb.csv"
    anomalies_path = tmp_path / "anomalies.jsonl"

    cmd = [
        sys.executable,
        "scripts/msb_compute.py",
        "--hy-csv",
        str(hy_path),
        "--vx1-csv",
        str(vx1_path),
        "--vx2-csv",
        str(vx2_path),
        "--spx-csv",
        str(spx_path),
        "--out",
        str(out_path),
        "--anomalies",
        str(anomalies_path),
        "--window",
        "20",
        "--fallback",
        "10",
        "--winsor",
        "0.1",
        "0.9",
    ]
    env = os.environ.copy()
    src_path = Path(__file__).resolve().parent.parent / "src"
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{existing}" if existing else str(src_path)
    )
    result = subprocess.run(
        cmd, check=True, capture_output=True, text=True, env=env
    )
    assert result.returncode == 0

    assert out_path.exists()
    assert anomalies_path.exists()
    entries = [json.loads(line) for line in anomalies_path.read_text().splitlines() if line.strip()]
    assert any(entry.get("kind") == "winsor_clip" for entry in entries)


def test_rule_b_uses_raw_deltas_by_default():
    idx = pd.bdate_range("2024-01-02", periods=6)
    hy = pd.Series([4.0, 4.0, 4.0, 4.0, 4.0, 10.0], index=idx)
    vx1 = pd.Series(18.0, index=idx)
    vx2 = pd.Series(20.0, index=idx)

    df_raw = compute_msb(
        hy=hy,
        vx1=vx1,
        vx2=vx2,
        window=5,
        fallback=3,
        lq=0.5,
        uq=0.5,
    )
    assert "B" in df_raw.iloc[-1]["triggers"]

    df_winsor = compute_msb(
        hy=hy,
        vx1=vx1,
        vx2=vx2,
        window=5,
        fallback=3,
        lq=0.5,
        uq=0.5,
        config=MSBConfig(rule_b_source="winsor"),
    )
    assert "B" not in df_winsor.iloc[-1]["triggers"]


def test_spx_ret_not_forward_filled_prevents_false_rule_a():
    idx = pd.bdate_range("2024-01-02", periods=3)
    hy = pd.Series(4.0, index=idx)
    vx1 = pd.Series(22.0, index=idx)
    vx2 = pd.Series(20.0, index=idx)
    spx = pd.Series(
        [-0.01, 0.01], index=pd.DatetimeIndex([idx[0], idx[2]])
    )

    df = compute_msb(hy=hy, vx1=vx1, vx2=vx2, spx_ret=spx, window=5, fallback=3)

    assert "A" in df.loc[idx[0], "triggers"]
    assert "A" not in df.loc[idx[1], "triggers"]
    assert "A" not in df.loc[idx[2], "triggers"]


def test_observed_union_calendar_does_not_fabricate_days():
    idx = pd.DatetimeIndex(["2024-01-02", "2024-01-04"])
    hy = pd.Series([4.0, 4.1], index=idx)
    vx1 = pd.Series([18.0, 18.2], index=idx)
    vx2 = pd.Series([20.0, 20.1], index=idx)

    df = compute_msb(hy=hy, vx1=vx1, vx2=vx2, window=5, fallback=3)
    assert list(df.index) == list(pd.to_datetime(idx).normalize())
    assert "2024-01-03" not in df.index.astype(str)


def test_rule_c_cooldown_boundary_behavior():
    idx = pd.bdate_range("2024-01-02", periods=40)
    hy = pd.Series(8.0, index=idx)
    vx1 = pd.Series(45.0, index=idx)
    vx2 = pd.Series(30.0, index=idx)
    spx = pd.Series(-0.002, index=idx)

    df = compute_msb(
        hy=hy, vx1=vx1, vx2=vx2, spx_ret=spx, window=20, fallback=5
    )
    trigger_dates = [i for i, flags in df["triggers"].items() if "C" in flags]
    assert trigger_dates
    first_trigger = trigger_dates[0]
    cooldown_until = (pd.Timestamp(first_trigger) + pd.tseries.offsets.BDay(5)).normalize()
    assert "C" not in df.loc[cooldown_until, "triggers"]
    later_triggers = [d for d in trigger_dates if d > cooldown_until]
    assert later_triggers
