import pytest
from ib_insync import Option
from portfolio_exporter.scripts.portfolio_greeks import list_positions
from unittest.mock import Mock

def test_option_contract_autofill_exchange():
    mock_ib = Mock()
    mock_position = Mock()
    mock_contract = Option(symbol='SPY', lastTradeDateOrContractMonth='20250117', strike=400, right='C')
    mock_position.contract = mock_contract
    mock_position.position = 100

    mock_ib.positions.return_value = [mock_position]
    mock_ib.qualifyContracts.return_value = [mock_contract]
    mock_ib.reqMktData.return_value = Mock(modelGreeks=Mock(delta=0.5))

    # Call the function under test
    list_positions(mock_ib)

    # Assert that the exchange was autofilled
    assert mock_contract.exchange == "SMART"
    assert mock_contract.currency == "USD"