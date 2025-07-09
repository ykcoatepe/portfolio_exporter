import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
import tempfile


class DummyContract:
    def __init__(self, conId=0, dt=""):
        self.conId = conId
        self.lastTradeDateOrContractMonth = dt


class Detail:
    def __init__(self, contract):
        self.contract = contract


class DummyIB:
    def __init__(self, mapping=None):
        self.mapping = mapping or {}

    def reqContractDetails(self, contract):
        key = getattr(contract, "lastTradeDateOrContractMonth", "") or getattr(
            contract, "symbol", ""
        )
        return self.mapping.get(key, [])


class Option:
    def __init__(self, symbol, expiry, strike, right, **kwargs):
        self.symbol = symbol
        self.lastTradeDateOrContractMonth = expiry
        self.strike = strike
        self.right = right
        self.__dict__.update(kwargs)


class Future:
    def __init__(self, symbol, exchange=None, lastTradeDateOrContractMonth=""):
        self.symbol = symbol
        self.exchange = exchange
        self.lastTradeDateOrContractMonth = lastTradeDateOrContractMonth


def load_module(mapping=None):
    ib_mod = types.ModuleType("ib_insync")
    ib_mod.IB = DummyIB
    ib_mod.Stock = type("Stock", (), {})
    ib_mod.Option = Option
    ib_mod.Future = Future
    ib_mod.Index = type("Index", (), {})
    ib_mod.util = types.SimpleNamespace()
    sys.modules["ib_insync"] = ib_mod

    module = types.ModuleType("ts")
    lines = Path("legacy/tech_signals_ibkr.py").read_text().splitlines()
    snippet = lines[:75] + lines[120:201]
    exec("\n".join(snippet), module.__dict__)
    module.ib = DummyIB(mapping)
    return module


class TechSignalsTests(unittest.TestCase):
    def test_norm_cdf(self):
        mod = load_module()
        self.assertAlmostEqual(mod._norm_cdf(0), 0.5, places=7)
        self.assertAlmostEqual(mod._norm_cdf(1), 0.8413, places=4)

    def test_bs_delta(self):
        mod = load_module()
        self.assertAlmostEqual(
            mod._bs_delta(100, 100, 0.5, 0.01, 0.2, True), 0.542235, places=6
        )
        self.assertAlmostEqual(
            mod._bs_delta(100, 100, 0.5, 0.01, 0.2, False), -0.457765, places=6
        )
        self.assertEqual(mod._bs_delta(-1, 100, 0.5, 0.01, 0.2), 0.0)

    def test_parse_ib_month(self):
        mod = load_module()
        self.assertEqual(mod._parse_ib_month("202401"), datetime(2024, 1, 1))
        self.assertEqual(mod._parse_ib_month("20240115"), datetime(2024, 1, 15))
        self.assertEqual(mod._parse_ib_month("bad"), datetime(1900, 1, 1))

    def test_first_valid_expiry(self):
        mapping = {
            "20240101": [Detail(DummyContract(1, "20240101"))],
            "20240201": [],
        }
        mod = load_module(mapping)
        mod.ib.mapping = mapping
        res = mod._first_valid_expiry("AAA", ["20240101", "20240201"], 100, "AAA")
        self.assertEqual(res, "20240101")

        mapping = {
            "20240101": [],
            "20240201": [Detail(DummyContract(2, "20240201"))],
        }
        mod = load_module(mapping)
        mod.ib.mapping = mapping
        res = mod._first_valid_expiry("AAA", ["20240101", "20240201"], 100, "AAA")
        self.assertEqual(res, "20240201")

        mapping = {
            "20240101": [],
            "20240201": [],
        }
        mod = load_module(mapping)
        mod.ib.mapping = mapping
        res = mod._first_valid_expiry("AAA", ["20240101", "20240201"], 100, "AAA")
        self.assertEqual(res, "20240101")

    def test_front_future(self):
        mapping = {
            "CL": [
                Detail(DummyContract(1, "202311")),
                Detail(DummyContract(2, "202402")),
            ]
        }
        mod = load_module(mapping)
        mod.ib.mapping = mapping

        class FixedDatetime(datetime):
            @classmethod
            def utcnow(cls):
                return cls(2023, 12, 15)

        mod.datetime = FixedDatetime
        fut = mod.front_future("CL", "NYMEX")
        self.assertEqual(fut.lastTradeDateOrContractMonth, "202402")

        mapping = {
            "CL": [
                Detail(DummyContract(3, "202301")),
                Detail(DummyContract(4, "202302")),
            ]
        }
        mod = load_module(mapping)
        mod.ib.mapping = mapping
        mod.datetime = FixedDatetime
        fut = mod.front_future("CL", "NYMEX")
        self.assertEqual(fut.lastTradeDateOrContractMonth, "202301")

    def test_load_tickers(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td, "missing.txt")
            good = Path(td, "tickers.txt")
            good.write_text("AAA\nBBB\n")
            mod.PORTFOLIO_FILES = [str(missing), str(good)]
            self.assertEqual(mod.load_tickers(), ["AAA", "BBB"])

    def test_load_tickers_no_file(self):
        mod = load_module()
        mod.PORTFOLIO_FILES = []
        with self.assertRaises(SystemExit):
            mod.load_tickers()


if __name__ == "__main__":
    unittest.main()
