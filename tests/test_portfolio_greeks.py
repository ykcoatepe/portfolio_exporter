import sys
import types
import importlib
import math
import unittest

try:  # optional deps
    import pandas as pd
    import numpy as np  # noqa: F401
except Exception as e:  # pragma: no cover - skip if missing
    raise unittest.SkipTest("pandas/numpy is not installed") from e

# Provide minimal ib_insync stub for module import
ib_mod = types.ModuleType("ib_insync")
for cls_name in [
    "Future",
    "IB",
    "Index",
    "Option",
    "Position",
    "Stock",
    "Ticker",
    "util",
]:
    setattr(ib_mod, cls_name, type(cls_name, (), {}))
sys.modules["ib_insync"] = ib_mod

contract_mod = types.ModuleType("ib_insync.contract")
setattr(contract_mod, "Contract", type("Contract", (), {}))
sys.modules["ib_insync.contract"] = contract_mod

pg = importlib.import_module("legacy.portfolio_greeks")
bs = importlib.import_module("utils.bs")


class BSGreeksTests(unittest.TestCase):
    def test_bs_greeks_call(self):
        g = bs.bs_greeks(100, 100, 0.5, 0.01, 0.2, True)
        self.assertAlmostEqual(g["delta"], 0.5422, places=4)
        self.assertAlmostEqual(g["gamma"], 0.02805, places=5)
        self.assertAlmostEqual(g["vega"], 0.2805, places=4)
        self.assertAlmostEqual(g["theta"], -0.0167, places=4)

    def test_bs_greeks_invalid(self):
        g = bs.bs_greeks(-10, 100, 0.5, 0.01, 0.2, True)
        for val in g.values():
            self.assertTrue(math.isnan(val))


class EDDRTests(unittest.TestCase):
    def test_eddr_basic(self):
        path = pd.Series([100, 90, 95, 80, 85, 70])
        dar, cdar = pg.eddr(path, horizon_days=3, alpha=0.5)
        self.assertAlmostEqual(dar, 0.1578947, places=6)
        self.assertAlmostEqual(cdar, 0.1640867, places=6)

    def test_eddr_insufficient(self):
        path = pd.Series([100, 101])
        dar, cdar = pg.eddr(path, horizon_days=3)
        self.assertTrue(math.isnan(dar))
        self.assertTrue(math.isnan(cdar))


class ListPositionsTests(unittest.TestCase):
    def test_list_positions_basic(self):
        class DummyIB:
            def portfolio(self):
                P = type("Pos", (), {})()
                C = type(
                    "Contract",
                    (),
                    {"secType": "OPT", "localSymbol": "A", "exchange": ""},
                )
                P.contract = C
                P.position = 1
                return [P]

            def qualifyContracts(self, contract):
                return [contract]

            def reqMktData(
                self,
                contract,
                genericTickList="",
                snapshot=False,
                regulatorySnapshot=False,
            ):
                G = type("Greeks", (), {"delta": 0.5})()
                T = type("Ticker", (), {"modelGreeks": G})()
                return T

            def sleep(self, t):
                pass

        prev = pg.TIMEOUT_SECONDS
        pg.TIMEOUT_SECONDS = 0
        try:
            result = pg.list_positions(DummyIB())
        finally:
            pg.TIMEOUT_SECONDS = prev
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0].position, 1)
        self.assertTrue(hasattr(result[0][1], "modelGreeks"))


if __name__ == "__main__":
    unittest.main()
