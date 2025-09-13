import builtins
import importlib
import types

import main


def test_auto_preflight_runs_portfolio_greeks(monkeypatch):
    # Stub daily_report preflight to return missing inputs first, then OK
    calls = {"daily": 0, "pg": 0}

    def fake_daily(argv):
        calls["daily"] += 1
        if calls["daily"] == 1:
            return {
                "ok": True,
                "outputs": [],
                "warnings": [
                    "missing positions csv",
                    "missing totals csv",
                    "missing combos csv",
                ],
                "meta": {"script": "daily_report"},
            }
        return {"ok": True, "outputs": [], "warnings": [], "meta": {"script": "daily_report"}}

    def fake_pg(argv):
        calls["pg"] += 1
        return {"ok": True, "outputs": [], "warnings": [], "meta": {"script": "portfolio_greeks"}}

    monkeypatch.setattr(
        "portfolio_exporter.scripts.daily_report.main", fake_daily
    )
    monkeypatch.setattr(
        "portfolio_exporter.scripts.portfolio_greeks.main", fake_pg
    )

    # Drive menu: 3 (Trades) → f (Preflight Daily Report) → r → 0
    importlib.reload(main)
    inp = iter(["3", "f", "r", "0"])  # enter Trades, preflight, back, exit
    monkeypatch.setattr(builtins, "input", lambda _="": next(inp))
    monkeypatch.setattr(main, "input", lambda _="": next(inp))
    main.parse_args = lambda: types.SimpleNamespace(
        quiet=True,
        format="csv",
        list_tasks=False,
        workflow=None,
        tasks=None,
        tasks_csv=None,
        dry_run=False,
        json=False,
    )
    main.main()
    assert calls["daily"] >= 2 and calls["pg"] == 1

