from portfolio_exporter.core.input import parse_order_line


def test_parse_call_spread():
    out = parse_order_line("SPY 620/630C 18-Oct-25 x2")
    assert out and out.underlying == "SPY" and out.qty == 2
    ks = sorted([leg.strike for leg in out.legs])
    assert ks == [620.0, 630.0] and out.legs[0].right == "C"


def test_parse_put_single():
    out = parse_order_line("QQQ 350p nov15")
    assert out and len(out.legs) == 1 and out.legs[0].right == "P"
