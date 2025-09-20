from ib_insync import Option
from portfolio_exporter.scripts.portfolio_greeks import list_positions_sync


def test_option_contract_autofill_exchange():
    class DummyIB:
        async def reqPositionsAsync(self):
            return [mock_position]

        async def qualifyContractsAsync(self, contract):
            return [contract]

        async def reqMktDataAsync(
            self,
            contract,
            genericTickList="",
            snapshot=False,
            regulatorySnapshot=False,
        ):
            class Greeks:
                delta = 0.5

            class Ticker:
                modelGreeks = Greeks()

            return Ticker()

        async def sleep(self, _):
            return None

    mock_ib = DummyIB()
    mock_position = type("Pos", (), {})()
    mock_contract = Option(
        symbol="SPY",
        lastTradeDateOrContractMonth="20250117",
        strike=400,
        right="C",
    )
    mock_contract.exchange = ""
    mock_contract.currency = ""
    mock_position.contract = mock_contract
    mock_position.position = 100

    # Call the function under test
    list_positions_sync(mock_ib)

    # Assert that the exchange was autofilled
    assert mock_contract.exchange == "SMART"
    assert mock_contract.currency == "USD"
