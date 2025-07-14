import yfinance as yf
from ib_insync import util, IB
from typing import Sequence, Dict


def _ibkr_quotes(tickers: Sequence[str]) -> Dict[str, float]:
    ib = IB()
    try:
        ib.connect("127.0.0.1", 7497, clientId=12, timeout=2)
    except Exception as e:
        raise ConnectionError(str(e))
    data = {}
    for t in tickers:
        contract = util.stock(t, "SMART", "USD")
        q = ib.reqMktData(contract, "", False, False)
        ib.sleep(1)
        if q.last:
            data[t] = q.last
    ib.disconnect()
    return data


def _yf_quotes(tickers: Sequence[str]) -> Dict[str, float]:
    df = yf.download(tickers, period="1d", interval="1m", progress=False)
    if isinstance(df, tuple):
        df = df[0]
    return {t: float(df["Close"][t].dropna()[-1]) for t in tickers}


def snapshot(tickers: Sequence[str]) -> Dict[str, float]:
    try:
        return _ibkr_quotes(tickers)
    except ConnectionError:
        return _yf_quotes(tickers)
