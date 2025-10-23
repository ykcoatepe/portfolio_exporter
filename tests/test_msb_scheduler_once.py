from __future__ import annotations

import csv
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


def test_msb_scheduler_once(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PSD_DB", str(tmp_path / "psd.db"))

    # Seed vendor CSVs
    idx = pd.bdate_range("2024-01-02", periods=8)
    hy = pd.Series([4.0, 4.05, 4.12, 4.2, 4.5, 4.7, 4.85, 5.1], index=idx)
    vx1 = pd.Series([20.0, 20.5, 21.0, 21.4, 22.5, 24.0, 25.0, 26.0], index=idx)
    vx2 = pd.Series([19.5, 19.8, 20.0, 20.2, 20.4, 20.6, 20.8, 21.0], index=idx)
    spx = pd.Series([-0.005] * len(idx), index=idx)

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
        idx[-1]
        .to_pydatetime()
        .replace(hour=17, minute=30, tzinfo=ZoneInfo("Europe/Istanbul"))
    )

    assert run_msb_scheduler_once(
        app,
        vendor_dir=vendor_dir,
        now=run_at,
    )

    history = store.read_msb_history(days=10)
    assert len(history) == 1
    assert history[0]["date"] == idx[-1].date().isoformat()

    alert_events = [payload for event, payload in events if event == "sentinel.alert"]
    assert alert_events, "expected sentinel.alert SSE event"
    assert any(payload.get("rule") in {"A", "B"} for payload in alert_events)

    livebar_path = Path("data") / "live_status_bar.csv"
    assert livebar_path.exists()
    with livebar_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert rows, "live status bar should contain at least one row"
    first = rows[0]
    assert set(first.keys()) == {
        "Hedge",
        "Cost % NAV",
        "Status",
        "Expiry",
        "Trigger",
        "TriggerTimeTRT",
        "Notes",
    }
    assert first["Trigger"] in {"RULE_A_VIX_BACKWARDATION", "RULE_B_HY_SHOCK"}
    assert first["Status"] == "STAGED"
