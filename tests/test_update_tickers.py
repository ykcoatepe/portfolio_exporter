import os
import unittest
from unittest.mock import patch
import tempfile

import legacy.update_tickers as ut


class UpdateTickersTests(unittest.TestCase):
    def test_save_tickers(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.txt")
            ut.save_tickers(["AAA", "VIX"], path)
            with open(path) as f:
                lines = f.read().splitlines()
        self.assertEqual(lines, ["AAA", "^VIX"])

    def test_fetch_ib_tickers_no_ib(self):
        with patch.object(ut, "IB", None):
            self.assertEqual(ut.fetch_ib_tickers(), [])

    def test_fetch_ib_tickers_success(self):
        class DummyIB:
            def connect(self, host, port, clientId, timeout):
                pass

            def positions(self):
                C = type("Contract", (), {})
                P = type("Position", (), {})
                p1 = P()
                p1.contract = C()
                p1.contract.symbol = "AAA"
                p1.contract.secType = "STK"
                p2 = P()
                p2.contract = C()
                p2.contract.symbol = "VIX"
                p2.contract.secType = "STK"
                return [p1, p2]

            def disconnect(self):
                pass

        with patch.object(ut, "IB", DummyIB):
            tickers = ut.fetch_ib_tickers()
        self.assertEqual(sorted(tickers), ["AAA", "VIX"])


if __name__ == "__main__":
    unittest.main()
