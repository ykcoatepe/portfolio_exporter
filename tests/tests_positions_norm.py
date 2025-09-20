from __future__ import annotations

from psd.ingestor.normalize import split_positions


def _stock_fixture():
    return {
        "secType": "STK",
        "symbol": "AAPL",
        "conId": 123,
        "qty": 10,
        "avg_cost": 150.0,
        "tick": {"last": 155.0, "ts": 1_700_000_000},
        "greeks": {"delta": 10.0},
    }


def _combo_parent():
    return {
        "secType": "BAG",
        "symbol": "AAPL",
        "description": "AAPL CALL SPREAD",
        "combo_legs": [
            {"conId": 2001},
            {"conId": 2002},
        ],
    }


def _combo_leg_long():
    return {
        "secType": "OPT",
        "symbol": "AAPL",
        "conId": 2001,
        "qty": 1,
        "avg_cost": 5.0,
        "multiplier": 100,
        "right": "CALL",
        "strike": 180.0,
        "expiry": "20240119",
        "tick": {"mid": 6.0, "ts": 1_700_000_000},
        "greeks": {"delta": 0.55, "gamma": 0.02, "theta": -0.10},
    }


def _combo_leg_short():
    return {
        "secType": "OPT",
        "symbol": "AAPL",
        "conId": 2002,
        "qty": -1,
        "avg_cost": 3.0,
        "multiplier": 100,
        "right": "CALL",
        "strike": 190.0,
        "expiry": "20240119",
        "tick": {"mid": 2.5, "ts": 1_700_000_000},
        "greeks": {"delta": -0.35, "gamma": -0.01, "theta": -0.04},
    }


def _single_option():
    return {
        "secType": "OPT",
        "symbol": "MSFT",
        "conId": 3001,
        "qty": 1,
        "avg_cost": 2.0,
        "multiplier": 100,
        "right": "PUT",
        "strike": 300.0,
        "expiry": "20240216",
        "tick": {"mid": 2.6, "ts": 1_700_000_000},
        "greeks": {"delta": -0.40, "theta": -0.02},
    }


def test_split_positions_groups_stock_combo_and_single_option():
    raw_positions = [
        _stock_fixture(),
        _combo_parent(),
        _combo_leg_long(),
        _combo_leg_short(),
        _single_option(),
    ]

    result = split_positions(raw_positions, "RTH")

    singles = result["single_stocks"]
    combos = result["option_combos"]
    singles_opts = result["single_options"]

    assert len(singles) == 1
    assert singles[0]["symbol"] == "AAPL"
    assert round(singles[0]["pnl_intraday"], 2) == 50.0

    assert len(combos) == 1
    combo = combos[0]
    assert combo["combo_id"]
    assert combo["name"] == "AAPL CALL SPREAD"
    assert round(combo["pnl_intraday"], 2) == 150.0
    assert len(combo["legs"]) == 2

    greeks_agg = combo["greeks_agg"]
    assert round(greeks_agg["delta"], 2) == 0.20
    assert round(greeks_agg["gamma"], 2) == 0.01
    assert round(greeks_agg["theta"], 2) == -0.14

    assert len(singles_opts) == 1
    assert singles_opts[0]["symbol"] == "MSFT"
    assert round(singles_opts[0]["pnl_intraday"], 2) == 60.0
