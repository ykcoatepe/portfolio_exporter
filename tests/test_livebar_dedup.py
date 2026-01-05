from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from psd.ui.livebar import update_live_status_bar


def test_livebar_dedup(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    livebar = Path("data") / "live_status_bar.csv"
    livebar.parent.mkdir(parents=True, exist_ok=True)

    with livebar.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "Hedge",
                "Cost % NAV",
                "Status",
                "Expiry",
                "Trigger",
                "TriggerTimeTRT",
                "Notes",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "Hedge": "Reduce beta (−20–40%)",
                "Cost % NAV": "—",
                "Status": "LIVE",
                "Expiry": "2024-03-20",
                "Trigger": "RULE_C_MSB_60x3D",
                "TriggerTimeTRT": "2024-03-13T17:30:00+03:00",
                "Notes": "",
            }
        )

    when = datetime(2024, 3, 14, 17, 30, tzinfo=ZoneInfo("Europe/Istanbul"))
    update_live_status_bar("C", when, msb=72, color="red", notes="cooldown until 2024-03-21")

    with livebar.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert len(rows) == 1
    notes_value = rows[0]["Notes"]
    assert "already hedged; maintain size" in notes_value
    assert "cooldown until 2024-03-21" in notes_value
