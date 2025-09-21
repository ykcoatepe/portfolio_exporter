import builtins
import importlib
import json
import os
from pathlib import Path

import main


def _drive_menu(monkeypatch, inputs, fmt="excel", quiet=True):
    inp = iter(inputs)
    mock_input = lambda _="": next(inp)
    # Route both top-level and prompt-aware inputs through the same iterator
    monkeypatch.setattr(builtins, "input", mock_input)
    monkeypatch.setattr(main, "input", mock_input)
    import portfolio_exporter.menus.trade as trade
    monkeypatch.setattr(trade, "prompt_input", mock_input)
    # Configure args
    main.parse_args = lambda: type(
        "Args",
        (),
        dict(
            quiet=quiet,
            format=fmt,
            list_tasks=False,
            workflow=None,
            tasks=None,
            tasks_csv=None,
            dry_run=False,
            json=False,
        ),
    )()


def test_trade_menu_format_toggle_affects_executions(monkeypatch):
    called = []
    monkeypatch.setattr(
        "portfolio_exporter.scripts.trades_report.run",
        lambda fmt="csv", **_: called.append(fmt),
    )
    importlib.reload(main)
    _drive_menu(monkeypatch, ["3", "t", "e", "r", "0"], fmt="excel", quiet=True)
    main.main()
    # Default excel toggled once -> pdf
    assert "pdf" in called


def test_open_last_ticket_copies_json(monkeypatch, tmp_path):
    # Prepare a fake ticket file
    ticket = {"strategy": "vertical", "legs": []}
    p = tmp_path / "order_ticket_foo.json"
    p.write_text(json.dumps(ticket))

    import portfolio_exporter.menus.trade as trade
    monkeypatch.setattr(trade, "_copy_to_clipboard", lambda txt: True)
    monkeypatch.setattr(
        "portfolio_exporter.core.io.latest_file", lambda base, fmt=None: str(p)
    )

    # Drive menu with non-quiet to trigger clipboard path
    importlib.reload(main)
    _drive_menu(monkeypatch, ["3", "k", "r", "0"], fmt="csv", quiet=False)
    main.main()


def test_filters_persist_in_memory(monkeypatch, tmp_path):
    # Set CWD to temp and prepare memory dir
    os.chdir(tmp_path)
    (tmp_path / ".codex").mkdir(exist_ok=True)
    (tmp_path / ".codex" / "memory.json").write_text(
        json.dumps({"preferences": {}, "decisions": [], "changelog": [], "tasks": [], "questions": [], "workflows": {}})
    )

    # Stub trades_report.main to emit outputs
    monkeypatch.setattr(
        "portfolio_exporter.scripts.trades_report.main",
        lambda argv: {"outputs": [str(tmp_path / "trades_filtered.csv")]},
    )
    # Point settings.output_dir to tmp_path
    class S:
        output_dir = tmp_path

    monkeypatch.setattr("portfolio_exporter.core.config.settings", S)

    # Inputs for Save filtered: symbols, effect, structure, top_n, then return and exit
    inputs = [
        "3",  # enter Trades
        "s",  # Save filtered CSV
        "AAPL,MSFT",  # symbols
        "Open",  # effect
        "vertical",  # structure
        "10",  # top N
        "r",
        "0",
    ]
    importlib.reload(main)
    _drive_menu(monkeypatch, inputs, fmt="csv", quiet=True)
    main.main()

    # Validate memory persisted
    data = json.loads((tmp_path / ".codex" / "memory.json").read_text())
    prefs = data.get("preferences", {}).get("trades_filters", {})
    assert prefs.get("symbols") == "AAPL,MSFT"
    assert prefs.get("effect") == "Open"
    assert prefs.get("structure") == "vertical"
    assert prefs.get("top_n") == 10

