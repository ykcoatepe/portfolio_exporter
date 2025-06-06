import unittest
from datetime import date

import pandas as pd


import trades_report as tr


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
                pd.to_datetime(r["date"]).date(),
                r["ticker"],
                r["side"],
                r["qty"],
                r["price"],
            )
            for r in data
        ]

    def test_filter_range(self):
        start, end = date(2024, 6, 1), date(2024, 6, 30)
        res = tr.filter_trades(self.trades, start, end)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].ticker, "A")
        self.assertEqual(res[1].ticker, "B")



if __name__ == "__main__":
    unittest.main()
