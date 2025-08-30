import unittest
from datetime import date

import pandas as pd


import legacy.trades_report as tr


class DatePhraseTests(unittest.TestCase):
    def test_today_phrase(self):
        ref = date(2024, 6, 15)
        start, end = tr.date_range_from_phrase("today", ref)
        self.assertEqual((start, end), (ref, ref))

    def test_yesterday_phrase(self):
        ref = date(2024, 6, 15)
        start, end = tr.date_range_from_phrase("yesterday", ref)
        self.assertEqual((start, end), (date(2024, 6, 14), date(2024, 6, 14)))

    def test_week_phrase(self):
        ref = date(2024, 6, 19)  # Wednesday
        start, end = tr.date_range_from_phrase("week", ref)
        self.assertEqual(start, date(2024, 6, 17))  # Monday
        self.assertEqual(end, ref)

    def test_month_phrase(self):
        ref = date(2024, 7, 2)
        start, end = tr.date_range_from_phrase("June", ref)
        self.assertEqual(start, date(2024, 6, 1))
        self.assertEqual(end, date(2024, 6, 30))

    def test_year_phrase(self):
        start, end = tr.date_range_from_phrase("2024", date(2024, 5, 1))
        self.assertEqual(start, date(2024, 1, 1))
        self.assertEqual(end, date(2024, 12, 31))


class FilterTradesTests(unittest.TestCase):
    def setUp(self):
        data = [
            {
                "date": "2024-06-01",
                "ticker": "A",
                "side": "BUY",
                "qty": 1,
                "price": 1.0,
            },
            {
                "date": "2024-06-10",
                "ticker": "B",
                "side": "BUY",
                "qty": 1,
                "price": 1.0,
            },
            {
                "date": "2024-07-01",
                "ticker": "C",
                "side": "BUY",
                "qty": 1,
                "price": 1.0,
            },
        ]
        self.trades = [
            tr.Trade(
                exec_id="0",
                perm_id=0,
                order_id=0,
                symbol=r["ticker"],
                sec_type="STK",
                currency="USD",
                expiry=None,
                strike=None,
                right=None,
                multiplier=None,
                exchange="",
                primary_exchange=None,
                trading_class=None,
                datetime=pd.to_datetime(r["date"]),
                side=r["side"],
                qty=r["qty"],
                price=r["price"],
                avg_price=r["price"],
                cum_qty=r["qty"],
                last_liquidity="",
                commission=None,
                commission_currency=None,
                realized_pnl=None,
                account=None,
                model_code=None,
                order_ref=None,
                combo_legs=None,
            )
            for r in data
        ]

    def test_filter_range(self):
        start, end = date(2024, 6, 1), date(2024, 6, 30)
        res = tr.filter_trades(self.trades, start, end)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].symbol, "A")
        self.assertEqual(res[1].symbol, "B")


class OpenOrderTests(unittest.TestCase):
    def setUp(self):
        self.combo_leg_data = [
            {
                "symbol": "SPY",
                "sec_type": "OPT",
                "expiry": "20240719",
                "strike": 500.0,
                "right": "C",
                "ratio": 1,
                "action": "BUY",
                "exchange": "SMART",
            },
            {
                "symbol": "SPY",
                "sec_type": "OPT",
                "expiry": "20240719",
                "strike": 505.0,
                "right": "C",
                "ratio": 1,
                "action": "SELL",
                "exchange": "SMART",
            },
        ]
        self.open_order_combo = tr.OpenOrder(
            order_id=1,
            perm_id=101,
            symbol="SPY",
            sec_type="BAG",
            currency="USD",
            expiry=None,
            strike=None,
            right=None,
            combo_legs=self.combo_leg_data,
            side="BUY",
            total_qty=1,
            lmt_price=1.50,
            aux_price=0.0,
            tif="DAY",
            order_type="LMT",
            algo_strategy=None,
            status="Submitted",
            filled=0,
            remaining=1,
            account="U1234567",
            order_ref="ComboOrder1",
        )
        self.open_order_single = tr.OpenOrder(
            order_id=2,
            perm_id=102,
            symbol="AAPL",
            sec_type="STK",
            currency="USD",
            expiry=None,
            strike=None,
            right=None,
            combo_legs=None,
            side="BUY",
            total_qty=10,
            lmt_price=170.0,
            aux_price=0.0,
            tif="DAY",
            order_type="LMT",
            algo_strategy=None,
            status="Submitted",
            filled=0,
            remaining=10,
            account="U1234567",
            order_ref="SingleOrder1",
        )

    def test_open_order_combo_legs(self):
        self.assertIsNotNone(self.open_order_combo.combo_legs)
        self.assertEqual(len(self.open_order_combo.combo_legs), 2)
        self.assertEqual(self.open_order_combo.combo_legs[0]["symbol"], "SPY")
        self.assertEqual(self.open_order_combo.combo_legs[1]["action"], "SELL")

    def test_open_order_no_combo_legs(self):
        self.assertIsNone(self.open_order_single.combo_legs)


if __name__ == "__main__":    unittest.main()
