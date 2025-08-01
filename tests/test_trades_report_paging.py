import pandas as pd
from datetime import date

from portfolio_exporter.scripts import trades_report


class DummyEvent(list):
    def __iadd__(self, other):
        self.append(other)
        return self

    def __isub__(self, other):
        self.remove(other)
        return self


class DummyContract:
    symbol = "AAPL"
    secType = "STK"
    currency = "USD"
    conId = 1
    comboLegs = None


class DummyExecution:
    execId = "1"
    permId = 1
    orderId = 1
    exchange = "NYSE"
    side = "BOT"
    shares = 1
    price = 100.0
    avgPrice = 100.0
    cumQty = 1
    lastLiquidity = 1
    acctNumber = "U1"
    modelCode = ""
    orderRef = ""
    time = "20240101 10:00:00"


class DummyExecDetail:
    contract = DummyContract()
    execution = DummyExecution()


class DummyIB:
    def __init__(self):
        self.commissionReportEvent = DummyEvent()

    def connect(self, *args, **kwargs):
        return None

    def reqExecutions(self, filt):
        return [DummyExecDetail()]

    def sleep(self, *args, **kwargs):
        return None

    def reqAllOpenOrders(self):
        return None

    def openTrades(self):
        return []

    def disconnect(self):
        return None


class DummyExecutionFilter:
    def __init__(self, *args, **kwargs):
        pass


def test_paged_query_writes_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(trades_report, "IB", DummyIB)
    monkeypatch.setattr(trades_report, "ExecutionFilter", DummyExecutionFilter)
    monkeypatch.setattr(
        trades_report, "prompt_date_range", lambda: (date(2024, 1, 1), date(2024, 1, 1))
    )

    saved = {}

    def fake_save(df: pd.DataFrame, name: str, fmt: str, outdir):
        path = tmp_path / f"{name}.csv"
        df.to_csv(path, index=False)
        saved["path"] = path
        saved["df"] = df
        return path

    monkeypatch.setattr("portfolio_exporter.core.io.save", fake_save)

    df = trades_report.run(fmt="csv", return_df=True)
    assert not df.empty
    assert saved["path"].exists()
    assert len(saved["df"]) == 1
