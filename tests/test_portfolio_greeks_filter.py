import os
import sys
import subprocess
import pandas as pd
import pytest


from portfolio_exporter.scripts.portfolio_greeks import list_positions


def test_list_positions_fill_exchange_and_currency():
    class DummyIB:
        def positions(self):
            P = type("Pos", (), {})()
            C = type(
                "Contract",
                (),
                {"secType": "OPT", "exchange": "", "currency": None},
            )()
            P.contract = C
            P.position = 1
            return [P]

        def qualifyContracts(self, contract):
            return [contract]

        def reqMktData(self, *args, **kwargs):
            return None

        def sleep(self, t):
            pass

    bundles = list_positions(DummyIB())
    assert bundles, "No positions returned"
    pos, _ = bundles[0]
    assert pos.contract.exchange == "SMART"
    assert pos.contract.currency == "USD"


#def test_calc_portfolio_greeks_skip_indices_and_total():
#    # sample exposures including an index ticker to be filtered
#    df = pd.DataFrame({
#        "underlying": ["AAPL", "VIX"],
#        "position": [1, 1],
#        "multiplier": [1, 1],
#        "delta": [2.0, 3.0],
#        "gamma": [0.1, 0.2],
#        "vega": [0.3, 0.4],
#        "theta": [0.0, 0.0],
#        "rho": [0.0, 0.0],
#    })
#    # holdings only include AAPL
#    holdings = pd.DataFrame({"underlying": ["AAPL"]})
#    res = calc_portfolio_greeks(df, holdings, include_indices=False)
#    # VIX should be skipped
#    assert "VIX" not in res.index
#    # only AAPL and total
#    assert set(res.index) == {"AAPL", "PORTFOLIO_TOTAL"}
#    assert res.loc["PORTFOLIO_TOTAL", "delta"] == res.loc["AAPL", "delta"]


@pytest.mark.parametrize("flag, expect_indices", [(False, False), (True, True)])
def test_cli_portfolio_greeks_filters_indices(tmp_path, flag, expect_indices):
    # Run the CLI with/without --include-indices and inspect output CSV
    env = os.environ.copy()
    env["PE_TEST_MODE"] = "1"
    env["OUTPUT_DIR"] = str(tmp_path)
    cmd = [sys.executable, "main.py", "--output-dir", str(tmp_path), "portfolio-greeks"]
    if flag:
        cmd.append("--include-indices")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    files = list(tmp_path.glob("portfolio_greeks_*.csv"))
    assert files, "No portfolio_greeks CSV generated"
    df_out = pd.read_csv(files[0], index_col=0)
    has_index = any(df_out.index.isin(["VIX"]))
    assert has_index == expect_indices
    assert "PORTFOLIO_TOTAL" in df_out.index.values