from datetime import datetime

from portfolio_exporter.core.market_clock import rth_window_tr, TZ_TR


def _fmt(dt):
    return dt.astimezone(TZ_TR).strftime("%H:%M")


def test_tr_times_dst_awareness():
    # This test checks that TR-local open is either 16:30 or 17:30 depending on US DST season.
    win = rth_window_tr()
    assert _fmt(win.open_tr) in ("16:30", "17:30")
    # Close is either 23:00 (DST) or 00:00 (standard time, next day in TR)
    assert _fmt(win.close_tr) in ("23:00", "00:00")

