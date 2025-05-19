import pandas as pd
from pandas.testing import assert_frame_equal
from unittest.mock import patch
import historic_prices as hp


def make_multiindex_df():
    index = pd.date_range("2024-01-01", periods=2)
    cols = pd.MultiIndex.from_product([
        ["AAPL", "MSFT"],
        ["Open", "High", "Low", "Close", "Adj Close", "Volume"],
    ])
    data = [[1,2,3,4,5,6,10,20,30,40,50,60], [7,8,9,10,11,12,70,80,90,100,110,120]]
    return pd.DataFrame(data, index=index, columns=cols)


def make_single_df():
    index = pd.date_range("2024-01-01", periods=2)
    data = {
        "Open": [1,7],
        "High": [2,8],
        "Low": [3,9],
        "Close": [4,10],
        "Adj Close": [5,11],
        "Volume": [6,12],
    }
    return pd.DataFrame(data, index=index)


def expected_result(ticker):
    return pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02"],
        "ticker": [ticker, ticker],
        "open": [1,7],
        "high": [2,8],
        "low": [3,9],
        "close": [4,10],
        "adj_close": [5,11],
        "volume": [6,12],
    })


def test_fetch_and_prepare_data_multiindex():
    df_multi = make_multiindex_df()
    with patch("historic_prices.yf.download", return_value=df_multi) as mock_dl:
        result = hp.fetch_and_prepare_data(["AAPL", "MSFT"])
        assert mock_dl.called
    expected = pd.concat([expected_result("AAPL"), expected_result("MSFT")], ignore_index=True)
    assert_frame_equal(result.reset_index(drop=True), expected)


def test_fetch_and_prepare_data_single():
    df_single = make_single_df()
    with patch("historic_prices.yf.download", return_value=df_single) as mock_dl:
        result = hp.fetch_and_prepare_data(["AAPL"])
        assert mock_dl.called
    expected = expected_result("AAPL")
    assert_frame_equal(result.reset_index(drop=True), expected)


def test_fetch_and_prepare_data_empty():
    with patch("historic_prices.yf.download"):
        try:
            hp.fetch_and_prepare_data([])
            assert False, "Expected ValueError"
        except ValueError:
            pass

