import sys
import types
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta

# Provide minimal stubs so import works without optional packages
try:
    import pandas  # noqa: F401
except Exception:
    pd_stub = types.ModuleType("pandas")
    pd_stub.DataFrame = type("DataFrame", (), {})
    sys.modules.setdefault("pandas", pd_stub)

try:
    import numpy  # noqa: F401
except Exception:
    np_stub = types.ModuleType("numpy")
    np_stub.nan = float("nan")
    np_stub.isnan = lambda x: x != x
    sys.modules.setdefault("numpy", np_stub)

try:
    import ib_insync  # noqa: F401
except Exception:
    ib_stub = types.ModuleType("ib_insync")
    for cls in ["IB", "Option", "Stock"]:
        setattr(ib_stub, cls, type(cls, (), {}))
    sys.modules.setdefault("ib_insync", ib_stub)

import importlib

oc = importlib.import_module("option_chain_snapshot")


class ChooseExpiryTests(unittest.TestCase):
    def test_weekly_within_seven_days(self):
        today = datetime.utcnow().date()
        exp_close = (today + timedelta(days=3)).strftime("%Y%m%d")
        exp_later = (today + timedelta(days=10)).strftime("%Y%m%d")
        result = oc.choose_expiry([exp_close, exp_later])
        self.assertEqual(result, exp_close)

    def test_first_friday(self):
        today = datetime.utcnow().date()
        # choose a date more than 7 days ahead that is a Friday
        days = 8
        while (today + timedelta(days=days)).weekday() != 4:
            days += 1
        friday = (today + timedelta(days=days)).strftime("%Y%m%d")
        other = (today + timedelta(days=days + 2)).strftime("%Y%m%d")
        result = oc.choose_expiry([other, friday])
        self.assertEqual(result, friday)


class PromptSymbolExpiriesTests(unittest.TestCase):
    def test_prompt_symbol_expiries(self):
        seq = iter(
            [
                "AAPL",
                "20240101,20240108",
                "TSLA",
                "",
                "",
            ]
        )
        with patch("builtins.input", lambda _: next(seq)):
            result = oc.prompt_symbol_expiries()
        self.assertEqual(result, {"AAPL": ["20240101", "20240108"], "TSLA": []})


class PickExpiryHintTests(unittest.TestCase):
    def test_day_month_hint(self):
        expirations = [
            "20240621",
            "20240628",
            "20240705",
        ]
        res1 = oc.pick_expiry_with_hint(expirations, "26 Jun")
        res2 = oc.pick_expiry_with_hint(expirations, "Jun 26")
        res3 = oc.pick_expiry_with_hint(expirations, "26/06")
        self.assertEqual(res1, "20240628")
        self.assertEqual(res2, "20240628")
        self.assertEqual(res3, "20240628")


class YFinanceFallbackTests(unittest.TestCase):
    def test_fetch_yf_open_interest(self):
        import pandas as pd

        class DummyOC:
            calls = pd.DataFrame({"strike": [100], "openInterest": [10]})
            puts = pd.DataFrame({"strike": [90], "openInterest": [5]})

        class DummyTicker:
            def __init__(self, sym):
                pass

            def option_chain(self, expiry):
                return DummyOC

        with patch("yfinance.Ticker", DummyTicker):
            data = oc.fetch_yf_open_interest("AAA", "20240101")
        self.assertEqual(data[(100.0, "C")], 10)
        self.assertEqual(data[(90.0, "P")], 5)


if __name__ == "__main__":
    unittest.main()
