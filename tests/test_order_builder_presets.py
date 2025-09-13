import json
import io
import contextlib

from portfolio_exporter.scripts import order_builder


def _run(args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        order_builder.cli(args)
    return json.loads(buf.getvalue())


def test_bull_put_preset():
    data = _run([
        "--preset",
        "bull_put",
        "--symbol",
        "XYZ",
        "--expiry",
        "2025-01-17",
        "--qty",
        "1",
        "--width",
        "5",
        "--json",
        "--no-files",
    ])
    assert data["ok"] is True
    assert data.get("ticket")
    rs = data.get("risk_summary")
    assert rs and {"max_gain", "max_loss", "breakevens"} <= rs.keys()


def test_iron_condor_preset():
    data = _run([
        "--preset",
        "iron_condor",
        "--symbol",
        "XYZ",
        "--expiry",
        "2025-01-17",
        "--qty",
        "1",
        "--wings",
        "5",
        "--json",
        "--no-files",
    ])
    assert data["ok"] is True
    assert data.get("ticket")
    rs = data.get("risk_summary")
    assert rs and {"max_gain", "max_loss", "breakevens"} <= rs.keys()


def test_calendar_preset():
    data = _run([
        "--preset",
        "calendar",
        "--symbol",
        "XYZ",
        "--expiry",
        "2025-02-14",
        "--qty",
        "1",
        "--json",
        "--no-files",
    ])
    assert data["ok"] is True
    assert data.get("ticket")
    assert "risk_summary" not in data or data.get("risk_summary") is not None
