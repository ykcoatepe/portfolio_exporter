import sys
import types
import unittest
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
        exp_close = (today + timedelta(days=3)).strftime('%Y%m%d')
        exp_later = (today + timedelta(days=10)).strftime('%Y%m%d')
        result = oc.choose_expiry([exp_close, exp_later])
        self.assertEqual(result, exp_close)

    def test_first_friday(self):
        today = datetime.utcnow().date()
        # choose a date more than 7 days ahead that is a Friday
        days = 8
        while (today + timedelta(days=days)).weekday() != 4:
            days += 1
        friday = (today + timedelta(days=days)).strftime('%Y%m%d')
        other = (today + timedelta(days=days+2)).strftime('%Y%m%d')
        result = oc.choose_expiry([other, friday])
        self.assertEqual(result, friday)


class PickExpiryWithHintTests(unittest.TestCase):
    def test_yyyymm_hint_third_friday(self):
        expirations = [
            "20240607",
            "20240614",
            "20240621",
            "20240628",
        ]
        result = oc.pick_expiry_with_hint(expirations, "202406")
        self.assertEqual(result, "20240621")

    def test_month_name_hint(self):
        expirations = [
            "20240517",
            "20240621",
            "20250620",
        ]
        result = oc.pick_expiry_with_hint(expirations, "June")
        self.assertEqual(result, "20240621")

    def test_fallback_when_hint_missing(self):
        expirations = ["20251205", "20251212", "20251219"]
        expected = oc.choose_expiry(sorted(expirations))
        result = oc.pick_expiry_with_hint(expirations, "March")
        self.assertEqual(result, expected)

if __name__ == '__main__':
    unittest.main()
