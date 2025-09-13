from portfolio_exporter.core.ui import run_with_spinner


def test_run_with_spinner_returns_value():
    assert run_with_spinner("msg", lambda x: x + 1, 41) == 42
