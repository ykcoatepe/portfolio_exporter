import unittest
from unittest.mock import patch
import pandas as pd


import historic_prices as hp


def make_multiindex_df(tickers):
    dates = pd.date_range("2024-01-01", periods=2, freq="D")
    cols = pd.MultiIndex.from_product(
        [tickers, ["Open", "High", "Low", "Close", "Adj Close", "Volume"]]
    )
    data = [
        list(range(1, len(cols) + 1)),
        list(range(len(cols) + 1, 2 * len(cols) + 1)),
    ]
    df = pd.DataFrame(data, index=dates, columns=cols)
    df.index.name = "Date"
    return df


def make_single_df(ticker):
    dates = pd.date_range("2024-01-01", periods=2, freq="D")
    cols = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    data = [
        list(range(1, len(cols) + 1)),
        list(range(len(cols) + 1, 2 * len(cols) + 1)),
    ]
    df = pd.DataFrame(data, index=dates, columns=cols)
    df.index.name = "Date"
    return df


class HistoricPricesTests(unittest.TestCase):
    def test_fetch_and_prepare_multiindex(self):
        tickers = ["AAA", "BBB"]
        df_sample = make_multiindex_df(tickers)
        with patch.object(hp.yf, "download", return_value=df_sample):
            result = hp.fetch_and_prepare_data(tickers)
        self.assertEqual(set(result.columns), {"date","ticker","open","high","low","close","adj_close","volume"})
        self.assertEqual(len(result), len(df_sample)*len(tickers))
        self.assertEqual(sorted(result["ticker"].unique()), tickers)

    def test_fetch_and_prepare_single(self):
        ticker = ["AAA"]
        df_sample = make_single_df(ticker[0])
        with patch.object(hp.yf, "download", return_value=df_sample):
            result = hp.fetch_and_prepare_data(ticker)
        self.assertEqual(set(result.columns), {"date","ticker","open","high","low","close","adj_close","volume"})
        self.assertEqual(len(result), len(df_sample))
        self.assertEqual(result["ticker"].unique().tolist(), ticker)

    def test_fetch_empty_list(self):
        with self.assertRaises(ValueError):
            hp.fetch_and_prepare_data([])

    def test_load_tickers_file_fallback(self):
        with patch.object(hp, "_tickers_from_ib", return_value=[]), \
             patch.object(hp, "EXTRA_TICKERS", []):
            with patch.object(hp, "PORTFOLIO_FILES", ["dummy.txt"]):
                # create temporary file
                import tempfile
                with tempfile.TemporaryDirectory() as td:
                    f = td+"/tickers.txt"
                    with open(f,"w") as fh:
                        fh.write("AAA\nVIX\n")
                    with patch.object(hp, "PORTFOLIO_FILES", [f]):
                        tickers = hp.load_tickers()
        self.assertEqual(sorted(tickers), ["AAA", "^VIX"])

    def test_load_tickers_ib(self):
        with patch.object(hp, "_tickers_from_ib", return_value=["BBB","VIX"]), \
             patch.object(hp, "EXTRA_TICKERS", ["SPY"]), \
             patch.object(hp, "PORTFOLIO_FILES", []):
            tickers = hp.load_tickers()
        self.assertEqual(sorted(tickers), ["BBB","SPY","^VIX"])


if __name__ == "__main__":
    unittest.main()
