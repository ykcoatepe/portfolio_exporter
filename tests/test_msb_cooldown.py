from __future__ import annotations

import types
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from psd.core import store
from psd.sentinel.sched import run_msb_scheduler_once
from psd.web.app import create_app
from psd.web.config import Settings


def _write_series(series: pd.Series, path: Path) -> None:
    frame = pd.DataFrame({"date": series.index, "value": series.values})
    frame.to_csv(path, index=False)


def _write_truncated(series: pd.Series, end_date: pd.Timestamp, path: Path) -> None:
    truncated = series.loc[:end_date].copy()
    _write_series(truncated, path)


def test_msb_cooldown(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PSD_DB", str(tmp_path / "psd.db"))

    idx = pd.bdate_range("2024-03-01", periods=12)
    hy = pd.Series(4.0, index=idx)
    hy.iloc[-7:] = 8.5
    vx1 = pd.Series(18.0, index=idx)
    vx1.iloc[-7:] = 55.0
    vx2 = pd.Series(20.0, index=idx)
    vx2.iloc[-7:] = 28.0
    spx = pd.Series(-0.003, index=idx)

    vendor_dir = Path("data") / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)

    app = create_app(Settings(test_mode=True, disable_background=True, sse_heartbeat_sec=1))
    alerts: list[dict[str, object]] = []

    def _capture(self, event_type: str, payload: dict[str, object]) -> None:
        if event_type == "sentinel.alert":
            alerts.append(payload)

    monkeypatch.setattr(
        app.state.sse,
        "broadcast",
        types.MethodType(_capture, app.state.sse),
    )

    for day in idx[-6:]:
        _write_truncated(hy, day, vendor_dir / "hy.csv")
        _write_truncated(vx1, day, vendor_dir / "vx1.csv")
        _write_truncated(vx2, day, vendor_dir / "vx2.csv")
        _write_truncated(spx, day, vendor_dir / "spx_ret.csv")
        run_at = day.to_pydatetime().replace(
            hour=17, minute=30, tzinfo=ZoneInfo("Europe/Istanbul")
        )
        run_msb_scheduler_once(app, vendor_dir=vendor_dir, now=run_at)

    history = store.read_msb_history(days=10)
    assert len(history) >= 6

    rule_c_events = [payload for payload in alerts if payload.get("rule") == "C"]
    assert len(rule_c_events) == 1, "Rule C should emit exactly once during cooldown window"
