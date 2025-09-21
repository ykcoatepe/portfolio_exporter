from portfolio_exporter.core.symbols import normalize_symbols


def test_alias_basic():
    m = {"FORD": "F", "GOOGLE": "GOOGL"}
    assert normalize_symbols(["ford", "ldi", "GOOGLE"], m) == ["F", "LDI", "GOOGL"]

