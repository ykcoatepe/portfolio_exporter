from __future__ import annotations

from pathlib import Path

from portfolio_exporter.core.ib_export import export_ib_basket, export_ib_notes


def test_export_ib_basket_and_notes(tmp_path: Path) -> None:
    orders = [
        {
            "symbol": "ABC",
            "structure": "DebitCall",
            "contracts": 2,
            "expiry": "2025-01-15",
            "long_leg": "C 100",
            "short_leg": "C 105",
            "limit": 2.35,
            "OCO_tp": 3.5,
            "OCO_sl": 1.2,
            "entry_trigger": "break vwap",
        },
        {
            "symbol": "XYZ",
            "structure": "BearCallCredit",
            "contracts": 1,
            "expiry": "2025-01-15",
            "long_leg": "C 120",
            "short_leg": "C 115",
            "limit": 1.05,
            "OCO_tp": 0.2,
            "OCO_sl": 2.0,
            "entry_trigger": "reject vwap",
        },
    ]
    path = tmp_path / "basket.csv"
    export_ib_basket(orders, str(path))
    assert path.exists()
    rows = path.read_text().strip().splitlines()
    # header + 4 rows
    assert len(rows) == 1 + 4

    notes = tmp_path / "notes.txt"
    export_ib_notes(orders, str(notes))
    assert notes.exists()
    txt = notes.read_text()
    assert "ABC DebitCall" in txt and "XYZ BearCallCredit" in txt

