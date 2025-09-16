from __future__ import annotations
# ruff: noqa: I001

import warnings
from typing import Any
import pandas as pd


def test_get_closes_no_future_warning(monkeypatch: Any) -> None:
    # Patch yfinance.download to avoid network and to ensure behavior
    seen = {"auto": None}

    class DummyYF:
        @staticmethod
        def download(tickers: str, period: str, interval: str, progress: bool, **kwargs):
            # Capture whether auto_adjust is explicitly provided
            seen["auto"] = kwargs.get("auto_adjust")
            # Return a small DataFrame with Close column
            return pd.DataFrame({"Close": [100.0, 101.0, 102.0]})

    monkeypatch.setitem(__import__("sys").modules, "yfinance", DummyYF())

    import src.psd.datasources.yfin as yfin

    with warnings.catch_warnings(record=True) as _w:
        warnings.simplefilter("error", FutureWarning)
        closes = yfin.get_closes("SPY", 3, {})
    assert isinstance(closes, list)
    assert seen["auto"] in (False, True)
