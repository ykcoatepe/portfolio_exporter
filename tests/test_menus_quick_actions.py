from __future__ import annotations

import sys
import types

import pytest

from portfolio_exporter.menus import trade


def test_open_last_report(monkeypatch, capsys, tmp_path):
    sample = tmp_path / "daily_report.html"

    def fake_latest(name, fmt="html", outdir=None):
        return sample

    monkeypatch.setattr("portfolio_exporter.core.io.latest_file", fake_latest)
    assert trade._resolve_last_report() == sample
    msg = trade.open_last_report(quiet=True)
    out = capsys.readouterr().out
    assert str(sample) in out
    assert msg.startswith("Opened")


def test_quick_save_filtered(monkeypatch, capsys):
    import portfolio_exporter.scripts.trades_report as tr_mod

    def fake_main(argv):
        return {"ok": True, "outputs": ["/tmp/a.csv", "/tmp/b.csv"]}

    monkeypatch.setattr(tr_mod, "main", fake_main)
    summary = trade._quick_save_filtered(output_dir="/tmp", symbols="AAPL", quiet=False)
    out = capsys.readouterr().out
    assert "/tmp/a.csv" in out and "/tmp/b.csv" in out
    assert summary["ok"] is True


def test_preview_json_and_clipboard(monkeypatch):
    import portfolio_exporter.scripts.trades_report as tr_mod

    def fake_main(argv):
        return {"ok": True}

    monkeypatch.setattr(tr_mod, "main", fake_main)
    txt = trade._preview_trades_json(symbols="AAPL")
    assert isinstance(txt, str)
    assert '"ok":true' in txt.replace(" ", "").lower()

    dummy = types.SimpleNamespace()
    dummy.copy = lambda t: setattr(dummy, "val", t)
    monkeypatch.setitem(sys.modules, "pyperclip", dummy)
    assert trade._copy_to_clipboard("hi") is True
    assert getattr(dummy, "val") == "hi"
    monkeypatch.delitem(sys.modules, "pyperclip")
    assert trade._copy_to_clipboard("hi") is False

