import pandas as pd
from portfolio_exporter.scripts import tech_scan

def test_rsi_calculation_handles_zero_division():
    # Create a series where the loss can be zero
    data = {'Close': [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 90, 80, 70, 60, 50, 40, 30, 20, 10]}
    df = pd.DataFrame(data)
    # Ensure no ZeroDivisionError is raised
    try:
        tech_scan._rsi(df['Close'])
    except ZeroDivisionError:
        assert False, "ZeroDivisionError was raised in _rsi calculation"