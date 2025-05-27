import unittest
from datetime import date
import pandas as pd

import net_liq_history_export as nlhe


class NetLiqHistoryExportTests(unittest.TestCase):
    def setUp(self):
        idx = pd.date_range("2024-01-01", periods=5, freq="D").date
        self.df = pd.DataFrame({"net_liq": range(5)}, index=idx)

    def test_parse_dates_sorts_and_converts(self):
        df = pd.DataFrame({"net_liq": [2, 1]}, index=["2024-01-02", "2024-01-01"])
        result = nlhe._parse_dates(df)
        self.assertEqual(list(result.index), [date(2024, 1, 1), date(2024, 1, 2)])
        for val in result.index:
            self.assertIsInstance(val, date)

    def test_filter_range_start_end(self):
        result = nlhe._filter_range(self.df, "2024-01-02", "2024-01-04")
        self.assertEqual(list(result.index), [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)])

    def test_filter_range_open_ended(self):
        result = nlhe._filter_range(self.df, None, "2024-01-03")
        self.assertEqual(list(result.index), [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)])


if __name__ == "__main__":
    unittest.main()
