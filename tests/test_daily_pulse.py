import unittest
import pandas as pd
import numpy as np
import tempfile
from pathlib import Path

import legacy.daily_pulse as dp


class DailyPulseTests(unittest.TestCase):
    def setUp(self):
        dates = pd.date_range("2024-01-01", periods=35, freq="D")
        data = {
            "date": list(dates) * 2,
            "ticker": ["AAA"] * 35 + ["BBB"] * 35,
            "open": np.arange(70),
            "high": np.arange(70) + 1,
            "low": np.arange(70),
            "close": np.arange(70) + 0.5,
            "adj_close": np.arange(70) + 0.5,
            "volume": np.ones(70) * 100,
        }
        self.df = pd.DataFrame(data)

    def test_indicator_columns(self):
        result = dp.compute_indicators(self.df)
        expected = {
            "sma20",
            "ema20",
            "atr14",
            "rsi14",
            "macd",
            "macd_signal",
            "bb_upper",
            "bb_lower",
            "vwap",
            "pct_change",
            "real_vol_30",
        }
        self.assertTrue(expected.issubset(result.columns))

    def test_missing_data(self):
        df = self.df.copy()
        df.loc[0, "close"] = np.nan
        result = dp.compute_indicators(df)
        self.assertEqual(len(result), len(df))

    def test_generate_report_file(self):
        df_ind = dp.compute_indicators(self.df)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "pulse.csv"
            dp.generate_report(df_ind, str(out))
            self.assertTrue(out.exists())
            saved = pd.read_csv(out, index_col=0)
            self.assertIn("close", saved.columns)


if __name__ == "__main__":
    unittest.main()
