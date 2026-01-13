from __future__ import annotations

import types
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.psd.core import store
from src.psd.sentinel.sched import run_msb_scheduler_once
from src.psd.web.app import create_app
from src.psd.web.config import Settings


def _write_series(series: pd.Series, path: Path) -> None:
    frame = pd.DataFrame({"date": series.index, "value": series.values})
    frame.to_csv(path, index=False)


def test_msb_scheduler_skips_when_stale(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PSD_DB", str(tmp_path / "psd.db"))
    monkeypatch.setenv("PSD_MSB_AUTO_REFRESH", "0")

    idx = pd.bdate_range("2024-01-02", periods=5)
    hy = pd.Series([4.0, 4.1, 4.2, 4.3, 4.4], index=idx)
    vx1 = pd.Series([20.0, 20.2, 20.4, 20.6, 20.8], index=idx)
    vx2 = pd.Series([19.5, 19.6, 19.7, 19.8, 19.9], index=idx)
    spx = pd.Series([0.001] * len(idx), index=idx)

    vendor_dir = Path("data") / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    _write_series(hy, vendor_dir / "hy.csv")
    _write_series(vx1, vendor_dir / "vx1.csv")
    _write_series(vx2, vendor_dir / "vx2.csv")
    _write_series(spx, vendor_dir / "spx_ret.csv")

    app = create_app(Settings(test_mode=True, disable_background=True, sse_heartbeat_sec=1))
    events: list[tuple[str, dict[str, object]]] = []

    def _capture(self, event_type: str, payload: dict[str, object]) -> None:
        events.append((event_type, payload))

    monkeypatch.setattr(
        app.state.sse,
        "broadcast",
        types.MethodType(_capture, app.state.sse),
    )

    run_at = (
        (idx[-1] + pd.Timedelta(days=2))
        .to_pydatetime()
        .replace(hour=17, minute=30, tzinfo=ZoneInfo("Europe/Istanbul"))
    )

    assert not run_msb_scheduler_once(app, vendor_dir=vendor_dir, now=run_at)

    history = store.read_msb_history(days=10)
    assert history == []

    alert_events = [payload for event, payload in events if event == "sentinel.alert"]
    assert not alert_events, "seed path should not emit sentinel.alert events"
