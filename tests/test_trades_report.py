import os
import sys
import subprocess
from datetime import date

import pandas as pd
import trades_report as tr


def test_get_date_range():
    ref = date(2025, 7, 2)
    start, end = tr.get_date_range(tr.DateOption.TODAY, ref)
    assert (start, end) == (ref, ref)
    start, end = tr.get_date_range(tr.DateOption.YESTERDAY, ref)
    assert (start, end) == (date(2025, 7, 1), date(2025, 7, 1))
    start, end = tr.get_date_range(tr.DateOption.WEEK_TO_DATE, ref)
    assert start == date(2025, 6, 30)
    assert end == ref
    start, end = tr.get_date_range(
        tr.DateOption.CUSTOM, ref, start=date(2025, 6, 1), end=date(2025, 6, 30)
    )
    assert (start, end) == (date(2025, 6, 1), date(2025, 6, 30))


def _sample_trade(d, ticker):
    return tr.Trade(
        exec_id="0",
        perm_id=0,
        order_id=0,
        symbol=ticker,
        sec_type="STK",
        currency="USD",
        expiry=None,
        strike=None,
        right=None,
        multiplier=None,
        exchange="",
        primary_exchange=None,
        trading_class=None,
        datetime=pd.to_datetime(d),
        side="BUY",
        qty=1,
        price=1.0,
        avg_price=1.0,
        cum_qty=1,
        last_liquidity="",
        commission=None,
        commission_currency=None,
        realized_pnl=None,
        account=None,
        model_code=None,
        order_ref=None,
        combo_legs=None,
    )


def _sample_order():
    return tr.OpenOrder(
        order_id=1,
        perm_id=1,
        symbol="AAPL",
        sec_type="STK",
        currency="USD",
        expiry=None,
        strike=None,
        right=None,
        combo_legs=None,
        side="BUY",
        total_qty=1,
        lmt_price=100.0,
        aux_price=0.0,
        tif="DAY",
        order_type="LMT",
        algo_strategy=None,
        status="Submitted",
        filled=0,
        remaining=1,
        account="U1",
        order_ref=None,
    )


def test_generate_trade_report_filters_and_includes_orders():
    trades = [
        _sample_trade("2025-06-30", "A"),
        _sample_trade("2025-07-01", "B"),
    ]
    orders = [_sample_order()]
    df_trades, df_orders = tr.generate_trade_report(
        trades,
        orders,
        tr.DateOption.CUSTOM,
        start=date(2025, 6, 30),
        end=date(2025, 6, 30),
    )
    assert len(df_trades) == 1
    assert df_trades.iloc[0]["symbol"] == "A"
    assert len(df_orders) == 1


def test_cli_report(tmp_path):
    env = os.environ.copy()
    env["PE_TEST_MODE"] = "1"
    cmd = [
        sys.executable,
        "main.py",
        "--output-dir",
        str(tmp_path),
        "report",
        "--date",
        "yesterday",
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    files = list(tmp_path.iterdir())
    assert len(files) == 2
