from __future__ import annotations

import json
from pathlib import Path

import builtins


def _make_positions():
    from src.psd.models import Position, OptionLeg

    legs = [
        OptionLeg(symbol="SPY", expiry="20300117", right="C", strike=410, qty=-1, price=2.0),
        OptionLeg(symbol="SPY", expiry="20300117", right="C", strike=415, qty=1, price=1.0),
    ]
    pos = Position(uid="pos1", symbol="SPY", sleeve="theta", kind="option", qty=0, mark=0.0, legs=legs)
    return [pos]


def _reset_engine_state():
    import src.psd.sentinel.engine as eng

    # Clear in-memory quieting state between tests
    eng._last_alert_ts.clear()
    eng._snooze_until.clear()
    eng._state_loaded = False


def test_debounce_duplicate_alerts(tmp_path: Path, monkeypatch) -> None:
    from src.psd.sentinel import engine as eng
    import src.psd.datasources.ibkr as ib

    _reset_engine_state()
    # Patch positions source
    monkeypatch.setattr(ib, "get_positions", lambda cfg=None: _make_positions(), raising=True)

    # Control time
    t0 = 1_700_000_000
    monkeypatch.setattr(eng, "_now_ts", lambda: t0, raising=True)

    memo_path = tmp_path / "memos.jsonl"
    cfg = {"memo_path": str(memo_path), "alerts": {"debounce_min": 5}, "nav": 100000.0}

    # First scan emits an alert
    dto1 = eng.scan_once(cfg)
    assert isinstance(dto1, dict)
    al1 = dto1.get("alerts", [])
    assert len(al1) == 1
    assert memo_path.exists()
    lines = memo_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1  # alert memo written

    # Second scan within 2 minutes should be suppressed
    monkeypatch.setattr(eng, "_now_ts", lambda: t0 + 120, raising=True)
    dto2 = eng.scan_once(cfg)
    assert len(dto2.get("alerts", [])) == 0
    content = memo_path.read_text(encoding="utf-8")
    # Look for a suppressed memo
    suppressed = [json.loads(l) for l in content.strip().splitlines() if l]
    assert any(m.get("type") == "suppressed" for m in suppressed)


def test_snooze_blocks_alert_and_writes_memo(tmp_path: Path, monkeypatch) -> None:
    from src.psd.sentinel import engine as eng
    import src.psd.datasources.ibkr as ib

    _reset_engine_state()
    monkeypatch.setattr(ib, "get_positions", lambda cfg=None: _make_positions(), raising=True)

    t0 = 1_700_100_000
    monkeypatch.setattr(eng, "_now_ts", lambda: t0, raising=True)

    memo_path = tmp_path / "memos.jsonl"
    uid = "SPY-20300117-credit_spread"  # derived by engine for the above positions
    rule = "combo"
    cfg = {"memo_path": str(memo_path), "alerts": {"debounce_min": 5}, "nav": 100000.0}

    # Set snooze for 30 minutes via cfg hook
    cfg["snooze"] = {"uid": uid, "rule": rule, "minutes": 30}
    dto = eng.scan_once(cfg)
    # No alert emitted
    assert len(dto.get("alerts", [])) == 0
    # Memos include 'snooze' command and a 'snoozed' evaluation note
    content = memo_path.read_text(encoding="utf-8")
    entries = [json.loads(l) for l in content.strip().splitlines() if l]
    assert any(m.get("type") == "snooze" and m.get("uid") == uid for m in entries)
    snotes = [m for m in entries if m.get("type") == "snoozed" and m.get("uid") == uid]
    assert snotes, "expected a 'snoozed' memo entry"
    next_ts = int(snotes[-1]["next"])  # type: ignore[index]
    assert next_ts == t0 + 30 * 60


def test_after_windows_alert_emits_again(tmp_path: Path, monkeypatch) -> None:
    from src.psd.sentinel import engine as eng
    import src.psd.datasources.ibkr as ib

    _reset_engine_state()
    monkeypatch.setattr(ib, "get_positions", lambda cfg=None: _make_positions(), raising=True)

    t0 = 1_700_200_000
    memo_path = tmp_path / "memos.jsonl"
    cfg = {"memo_path": str(memo_path), "alerts": {"debounce_min": 5}, "nav": 100000.0}

    # First emit
    monkeypatch.setattr(eng, "_now_ts", lambda: t0, raising=True)
    dto1 = eng.scan_once(cfg)
    assert len(dto1.get("alerts", [])) == 1

    # Within debounce → suppressed
    monkeypatch.setattr(eng, "_now_ts", lambda: t0 + 60, raising=True)
    dto2 = eng.scan_once(cfg)
    assert len(dto2.get("alerts", [])) == 0

    # After debounce window → emits again
    monkeypatch.setattr(eng, "_now_ts", lambda: t0 + 6 * 60, raising=True)
    dto3 = eng.scan_once(cfg)
    assert len(dto3.get("alerts", [])) == 1
