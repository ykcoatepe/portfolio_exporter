import logging
import pandas as pd
from unittest.mock import patch

from src import utils


def test_ib_first_quote_fallback(caplog):
    class DummyIB:
        def connect(self, *a, **k):
            raise TimeoutError

    def fake_yf(tickers):
        return pd.DataFrame({"ticker": tickers, "last": [1.0] * len(tickers)})

    with patch("src.utils.data_fetching.IB", return_value=DummyIB()):
        with patch("src.utils.data_fetching.fetch_yf_quotes", fake_yf):
            caplog.set_level(logging.WARNING)
            df = utils.ib_first_quote(["AAA"], ib_timeout=0.1)
    assert not df.empty
    assert "IBKR quote fetch failed" in caplog.text
