from pathlib import Path
from unittest.mock import patch

from portfolio_exporter.scripts import update_tickers as ut


def test_fetch_ib_symbols_no_ib():
    with patch.object(ut, "IB", None):
        equities, option_underlyings, option_contracts = ut.fetch_ib_symbols()
    assert equities == []
    assert option_underlyings == []
    assert option_contracts == 0


def test_fetch_ib_symbols_with_options():
    class DummyContract:
        def __init__(self, symbol, sec_type, **kwargs):
            self.symbol = symbol
            self.secType = sec_type
            for key, value in kwargs.items():
                setattr(self, key, value)

    class DummyPosition:
        def __init__(self, contract):
            self.contract = contract

    class DummyIB:
        def connect(self, host, port, clientId, timeout):
            return None

        def positions(self):
            return [
                DummyPosition(DummyContract("AAA", "STK")),
                DummyPosition(
                    DummyContract(
                        "VIX",
                        "OPT",
                        lastTradeDateOrContractMonth="20240621",
                        strike=15,
                        right="C",
                    )
                ),
            ]

        def disconnect(self):
            return None

    with patch.object(ut, "IB", DummyIB):
        equities, option_underlyings, option_contracts = ut.fetch_ib_symbols()

    assert equities == ["AAA"]
    assert option_underlyings == ["VIX"]
    assert option_contracts == 1


def test_run_writes_unique_tickers(tmp_path, monkeypatch):
    def fake_fetch():
        return ["AAA"], ["VIX", "AAA"], 2

    monkeypatch.setattr(ut.settings, "output_dir", str(tmp_path))
    with patch.object(ut, "fetch_ib_symbols", fake_fetch):
        ut.run()

    written = (Path(tmp_path) / ut.TICKERS_FILE).read_text().splitlines()
    assert written == ["AAA", "^VIX"]
