import pandas as pd
from typing import List, Tuple


class DummyIB:
    def __init__(self):
        self.connected = False

    def connect(self, *a, **k):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def positions(self):
        return []

    def isConnected(self):
        return self.connected


class DummyContract:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.secType = "STK"
        self.conId = 1


class DummyPos:
    def __init__(self, symbol: str):
        self.contract = DummyContract(symbol)
        self.position = 1


class DummyTicker:
    def __init__(self):
        g = type(
            "Greeks", (), dict(delta=0.5, gamma=0.1, vega=0.2, theta=0.1, rho=0.0)
        )()
        self.modelGreeks = g


# sample small dataframe helpers


def fetch_ohlc(tickers: List[str], days_back: int = 60) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=2, freq="D").strftime("%Y-%m-%d")
    rows = []
    for t in tickers:
        for i, d in enumerate(dates):
            rows.append(
                {
                    "date": d,
                    "ticker": t,
                    "open": i,
                    "high": i + 1,
                    "low": i,
                    "close": i + 0.5,
                    "adj_close": i + 0.5,
                    "volume": 100,
                }
            )
    return pd.DataFrame(rows)


def fetch_ib_quotes(ib, contracts) -> pd.DataFrame:
    rows = []
    for i, c in enumerate(contracts):
        sym = getattr(c, "symbol", f"C{i}")
        rows.append({"ticker": sym, "last": 1.0, "source": "IB"})
    return pd.DataFrame(rows)


def fetch_yf_quotes(tickers: List[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": tickers,
            "last": [1.0] * len(tickers),
            "source": ["YF"] * len(tickers),
        }
    )


def snapshot_chain(ib, symbol: str, expiry_hint: str | None = None) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol],
            "expiry": [expiry_hint or "20250101"],
            "strike": [100.0],
            "right": ["C"],
        }
    )


def load_ib_positions_ib(*a, **k) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAPL"],
            "side": ["Long"],
            "quantity": [1],
            "cost basis": [1.0],
            "mark price": [1.1],
        }
    )


def list_positions(ib) -> List[Tuple[DummyPos, DummyTicker]]:
    return [(DummyPos("AAPL"), DummyTicker())]


def get_portfolio_contracts(ib) -> List[DummyContract]:
    return [DummyContract("AAPL")]
