from __future__ import annotations

from pathlib import Path

from portfolio_exporter.scripts.micro_momo_sentinel import main as sentinel_main


def test_sentinel_posts_thread_ts(monkeypatch, tmp_path: Path):
    # Prepare a scored CSV with levels that will immediately trigger for long direction
    scored = tmp_path / "scored.csv"
    scored.write_text(
        "symbol,direction,vwap,orb_high\nABC,long,10,9.5\n",
        encoding="utf-8",
    )

    # Monkeypatch IB provider to return snapshot and bars for high RVOL
    from portfolio_exporter.core import providers as providers_pkg

    def fake_get_quote(sym, cfg):  # noqa: ANN001
        return {"last": 11.0}

    def fake_get_intraday_bars(sym, cfg, minutes=5, prepost=True):  # noqa: ANN001
        bars = []
        # 20 bars with low volume
        bars += [{"volume": 100, "close": 10.0}] * 20
        # last 5 bars high volume to boost RVOL
        bars += [{"volume": 500, "close": 10.5}] * 5
        return bars

    monkeypatch.setattr(
        providers_pkg.ib_provider, "get_quote", fake_get_quote, raising=True
    )
    monkeypatch.setattr(
        providers_pkg.ib_provider, "get_intraday_bars", fake_get_intraday_bars, raising=True
    )

    # Capture emit_alerts call
    captured = {"called": False, "per_item": None, "extra": None}

    def fake_emit(alerts, url, dry_run, offline, per_item=False, extra=None):  # noqa: ANN001
        captured["called"] = True
        captured["per_item"] = per_item
        captured["extra"] = extra
        return {"sent": len(alerts), "failed": []}

    monkeypatch.setattr(
        "portfolio_exporter.scripts.micro_momo_sentinel.emit_alerts", fake_emit, raising=True
    )

    # Stop the loop after first iteration
    def stop_sleep(_):  # noqa: ANN001
        raise SystemExit(0)

    monkeypatch.setattr("time.sleep", stop_sleep, raising=True)

    try:
        sentinel_main(
            [
                "--scored-csv",
                str(scored),
                "--out_dir",
                str(tmp_path),
                "--interval",
                "1",
                "--webhook",
                "http://example.com",
                "--thread",
                "12345",
            ]
        )
    except SystemExit:
        pass

    assert captured["called"] is True
    assert captured["per_item"] is True
    assert isinstance(captured["extra"], dict) and captured["extra"].get("thread_ts") == "12345"
