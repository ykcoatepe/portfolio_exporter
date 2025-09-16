from __future__ import annotations

import portfolio_exporter.main as pe_main
from portfolio_exporter.scripts import micro_momo_go


def test_micro_momo_go_stops_when_analyzer_fails(monkeypatch, tmp_path) -> None:
    def _fail_dashboard(argv):  # pragma: no cover - executed only on regression
        raise AssertionError("dashboard should not run when analyzer fails")

    def _fail_publish(*args, **kwargs):  # pragma: no cover - executed only on regression
        raise AssertionError("publish should not run when analyzer fails")

    def _fail_open(*args, **kwargs):  # pragma: no cover - executed only on regression
        raise AssertionError("open_dashboard should not run when analyzer fails")

    monkeypatch.setattr("portfolio_exporter.scripts.micro_momo_analyzer.main", lambda argv: 2)
    monkeypatch.setattr("portfolio_exporter.scripts.micro_momo_dashboard.main", _fail_dashboard)
    monkeypatch.setattr("portfolio_exporter.core.publish.publish_pack", _fail_publish)
    monkeypatch.setattr("portfolio_exporter.core.publish.open_dashboard", _fail_open)

    rc = micro_momo_go.main(["--out_dir", str(tmp_path)])
    assert rc == 2


def test_task_runner_passes_memory_symbols(monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    def _fake_go(argv: list[str]) -> int:
        captured["argv"] = list(argv)
        return 0

    monkeypatch.setattr("portfolio_exporter.scripts.micro_momo_go.main", _fake_go)
    monkeypatch.setattr("portfolio_exporter.core.memory.get_pref", lambda key: "Ford, tsla" if key == "micro_momo.symbols" else "")
    monkeypatch.setattr("portfolio_exporter.core.symbols.load_alias_map", lambda paths: {})
    monkeypatch.setattr(
        "portfolio_exporter.core.symbols.normalize_symbols",
        lambda symbols, alias_map: [s.strip().upper() for s in symbols if s.strip()],
    )

    for var in [
        "MOMO_SYMBOLS",
        "MOMO_CFG",
        "MOMO_OUT",
        "MOMO_PROVIDERS",
        "MOMO_DATA_MODE",
        "MOMO_WEBHOOK",
        "MOMO_THREAD",
        "MOMO_OFFLINE",
        "MOMO_AUTO_PRODUCERS",
        "MOMO_START_SENTINEL",
        "MOMO_ALIASES_PATH",
    ]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PE_TEST_MODE", "1")

    rc = pe_main.main(["--task", "micro-momo-go"])
    assert rc == 0
    argv = captured.get("argv")
    assert argv is not None, "micro_momo_go.main should be invoked"
    assert "--symbols" in argv
    idx = argv.index("--symbols")
    assert argv[idx + 1] == "FORD,TSLA"
