import pandas as pd

from portfolio_exporter.core.combo import detect_combos


def test_detects_verticals_and_straddles(tmp_path, monkeypatch):
    df = pd.DataFrame(
        [
            {
                "underlying": "AAPL",
                "qty": 1,
                "right": "C",
                "strike": 100,
                "expiry": "20240119",
                "delta": 0.5,
                "gamma": 0.1,
                "vega": 0.2,
                "theta": -0.05,
            },
            {
                "underlying": "AAPL",
                "qty": -1,
                "right": "C",
                "strike": 105,
                "expiry": "20240119",
                "delta": -0.4,
                "gamma": -0.08,
                "vega": -0.15,
                "theta": 0.04,
            },
            {
                "underlying": "MSFT",
                "qty": 1,
                "right": "C",
                "strike": 300,
                "expiry": "20240119",
                "delta": 0.6,
                "gamma": 0.05,
                "vega": 0.1,
                "theta": -0.02,
            },
            {
                "underlying": "MSFT",
                "qty": 1,
                "right": "P",
                "strike": 300,
                "expiry": "20240119",
                "delta": -0.4,
                "gamma": 0.04,
                "vega": 0.09,
                "theta": -0.01,
            },
            {
                "underlying": "TSLA",
                "qty": 1,
                "right": "C",
                "strike": 200,
                "expiry": "20240119",
                "delta": 0.3,
                "gamma": 0.02,
                "vega": 0.05,
                "theta": -0.01,
            },
        ],
        index=[101, 102, 201, 202, 301],
    )

    combos = detect_combos(df)

    assert len(combos) == 3
    structures = set(combos.structure)
    assert structures == {"VertCall", "Straddle", "Single"}

    vert = combos[combos.structure == "VertCall"].iloc[0]
    assert set(vert.legs) == {101, 102}

    straddle = combos[combos.structure == "Straddle"].iloc[0]
    assert set(straddle.legs) == {201, 202}

    single = combos[combos.structure == "Single"].iloc[0]
    assert single.legs == [301]
