from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from positions_engine.combos import (
    ComboStrategy,
    OptionCombo,
    OptionLegSnapshot,
    group_option_combos,
)
from positions_engine.core.models import (
    Instrument,
    InstrumentType,
    Position,
    Quote,
    TradingSession,
)
from positions_engine.service.state import PositionsState

NOW = datetime(2025, 2, 15, 15, 30, tzinfo=UTC)


def make_leg(
    *,
    leg_id: str,
    symbol: str,
    underlying: str,
    expiry: str,
    dte: int,
    right: str,
    strike: str,
    quantity: str,
    avg_cost: str,
    mark: str,
    mark_source: str,
    stale_seconds: int,
    delta: str,
    gamma: str,
    theta: str,
    vega: str,
) -> OptionLegSnapshot:
    return OptionLegSnapshot(
        leg_id=leg_id,
        instrument_symbol=symbol,
        account="acct-1",
        underlying=underlying,
        expiry=expiry,
        dte=dte,
        right=right,
        strike=Decimal(strike),
        quantity=Decimal(quantity),
        ratio=abs(Decimal(quantity)) or Decimal("1"),
        multiplier=Decimal("100"),
        avg_cost=Decimal(avg_cost),
        mark=Decimal(mark),
        mark_source=mark_source,
        stale_seconds=stale_seconds,
        previous_close=None,
        delta=Decimal(delta),
        gamma=Decimal(gamma),
        theta=Decimal(theta),
        vega=Decimal(vega),
        iv=None,
        day_pnl=Decimal("0"),
        total_pnl=Decimal("0"),
        day_basis=None,
        total_basis=None,
        notes=tuple(),
    )


def make_combo(
    *,
    combo_id: str,
    strategy: ComboStrategy,
    underlying: str,
    dte: int,
    net_price: str,
    delta: str,
    gamma: str,
    theta: str,
    vega: str,
    legs: tuple[OptionLegSnapshot, ...],
) -> OptionCombo:
    return OptionCombo(
        combo_id=combo_id,
        strategy=strategy,
        account="acct-1",
        underlying=underlying,
        dte=dte,
        net_price=Decimal(net_price),
        sum_delta=Decimal(delta),
        sum_gamma=Decimal(gamma),
        sum_theta=Decimal(theta),
        sum_vega=Decimal(vega),
        day_pnl=Decimal("0"),
        total_pnl=Decimal("0"),
        day_pnl_percent=None,
        total_pnl_percent=None,
        legs=legs,
        notes=tuple(),
    )


def test_group_option_combos_cancels_offsetting_verticals() -> None:
    short_lower = make_leg(
        leg_id="leg-short-lower",
        symbol="MSFT 20240517C00315000",
        underlying="MSFT",
        expiry="2024-05-17",
        dte=30,
        right="CALL",
        strike="315",
        quantity="-1",
        avg_cost="2.10",
        mark="2.05",
        mark_source="MID",
        stale_seconds=30,
        delta="-0.45",
        gamma="0.03",
        theta="-0.25",
        vega="-2.8",
    )
    short_upper = make_leg(
        leg_id="leg-short-upper",
        symbol="MSFT 20240517C00320000",
        underlying="MSFT",
        expiry="2024-05-17",
        dte=30,
        right="CALL",
        strike="320",
        quantity="1",
        avg_cost="1.40",
        mark="1.38",
        mark_source="MID",
        stale_seconds=30,
        delta="0.32",
        gamma="-0.02",
        theta="0.18",
        vega="1.9",
    )
    short_vertical = make_combo(
        combo_id="combo-vertical-short",
        strategy=ComboStrategy.VERTICAL,
        underlying="MSFT",
        dte=30,
        net_price="0.70",
        delta="-6.5",
        gamma="0.5",
        theta="6.0",
        vega="-5.4",
        legs=(short_lower, short_upper),
    )

    long_lower = make_leg(
        leg_id="leg-long-lower",
        symbol="MSFT 20240517C00315000",
        underlying="MSFT",
        expiry="2024-05-17",
        dte=30,
        right="CALL",
        strike="315",
        quantity="1",
        avg_cost="2.10",
        mark="2.05",
        mark_source="MID",
        stale_seconds=30,
        delta="0.45",
        gamma="-0.03",
        theta="0.25",
        vega="2.8",
    )
    long_upper = make_leg(
        leg_id="leg-long-upper",
        symbol="MSFT 20240517C00320000",
        underlying="MSFT",
        expiry="2024-05-17",
        dte=30,
        right="CALL",
        strike="320",
        quantity="-1",
        avg_cost="1.40",
        mark="1.38",
        mark_source="MID",
        stale_seconds=30,
        delta="-0.32",
        gamma="0.02",
        theta="-0.18",
        vega="-1.9",
    )
    long_vertical = make_combo(
        combo_id="combo-vertical-long",
        strategy=ComboStrategy.VERTICAL,
        underlying="MSFT",
        dte=30,
        net_price="-0.70",
        delta="6.1",
        gamma="-0.5",
        theta="-5.8",
        vega="5.2",
        legs=(long_lower, long_upper),
    )

    result = group_option_combos((short_vertical, long_vertical))
    assert len(result.groups) == 1

    group = result.groups[0]
    assert group.group_qty == Decimal("0")
    payload = group.to_payload()
    assert payload["group_qty"] == 0.0


def test_group_option_combos_merges_duplicate_condors() -> None:
    leg_specs = [
        {
            "leg_id": "leg-put-short-1",
            "symbol": "SPY 20251018P00395000",
            "right": "PUT",
            "strike": "395",
            "quantity": "-1",
            "avg_cost": "1.60",
            "mark": "1.50",
            "mark_source": "PREV",
            "stale_seconds": 180,
            "delta": "-0.20",
            "gamma": "0.01",
            "theta": "-0.40",
            "vega": "-3.5",
        },
        {
            "leg_id": "leg-put-long-1",
            "symbol": "SPY 20251018P00400000",
            "right": "PUT",
            "strike": "400",
            "quantity": "1",
            "avg_cost": "0.40",
            "mark": "0.35",
            "mark_source": "LAST",
            "stale_seconds": 90,
            "delta": "0.12",
            "gamma": "-0.01",
            "theta": "0.18",
            "vega": "1.6",
        },
        {
            "leg_id": "leg-call-short-1",
            "symbol": "SPY 20251018C00440000",
            "right": "CALL",
            "strike": "440",
            "quantity": "-1",
            "avg_cost": "1.20",
            "mark": "1.08",
            "mark_source": "MID",
            "stale_seconds": 75,
            "delta": "0.22",
            "gamma": "0.01",
            "theta": "-0.30",
            "vega": "-2.8",
        },
        {
            "leg_id": "leg-call-long-1",
            "symbol": "SPY 20251018C00445000",
            "right": "CALL",
            "strike": "445",
            "quantity": "1",
            "avg_cost": "0.32",
            "mark": "0.28",
            "mark_source": "MID",
            "stale_seconds": 60,
            "delta": "-0.14",
            "gamma": "-0.01",
            "theta": "0.16",
            "vega": "1.4",
        },
    ]

    legs_one = tuple(
        make_leg(
            leg_id=spec["leg_id"],
            symbol=spec["symbol"],
            underlying="SPY",
            expiry="2025-10-18",
            dte=28,
            right=spec["right"],
            strike=spec["strike"],
            quantity=spec["quantity"],
            avg_cost=spec["avg_cost"],
            mark=spec["mark"],
            mark_source=spec["mark_source"],
            stale_seconds=spec["stale_seconds"],
            delta=spec["delta"],
            gamma=spec["gamma"],
            theta=spec["theta"],
            vega=spec["vega"],
        )
        for spec in leg_specs
    )

    legs_two = tuple(
        make_leg(
            leg_id=f"{spec['leg_id']}-dup",
            symbol=spec["symbol"],
            underlying="SPY",
            expiry="2025-10-18",
            dte=28,
            right=spec["right"],
            strike=spec["strike"],
            quantity=spec["quantity"],
            avg_cost=str(Decimal(spec["avg_cost"]) * Decimal("1.05")),
            mark=str(Decimal(spec["mark"]) * Decimal("1.02")),
            mark_source=spec["mark_source"],
            stale_seconds=spec["stale_seconds"] + 15,
            delta=spec["delta"],
            gamma=spec["gamma"],
            theta=spec["theta"],
            vega=spec["vega"],
        )
        for spec in leg_specs
    )

    combo_one = make_combo(
        combo_id="combo-condor-1",
        strategy=ComboStrategy.IRON_CONDOR,
        underlying="SPY",
        dte=28,
        net_price="1.10",
        delta="-8.0",
        gamma="1.2",
        theta="11.0",
        vega="-7.2",
        legs=legs_one,
    )
    combo_two = make_combo(
        combo_id="combo-condor-2",
        strategy=ComboStrategy.IRON_CONDOR,
        underlying="SPY",
        dte=28,
        net_price="1.30",
        delta="-7.4",
        gamma="1.1",
        theta="10.6",
        vega="-6.9",
        legs=legs_two,
    )

    result = group_option_combos((combo_one, combo_two))
    assert len(result.groups) == 1

    group = result.groups[0]
    assert (
        group.combo_group_id
        == "IRON_CONDOR|SPY|C:440/445@2025-10-18|P:395/400@2025-10-18"
    )
    assert group.group_qty == Decimal("-2")
    assert group.mark_source == "MID"

    payload = group.to_payload()
    assert payload["group_qty"] == -2.0
    assert payload["group_net_price"] == 1.2
    assert payload["label"] == "SPY 395/400P + 440/445C • 28d • Credit 1.20"
    assert payload["mark_source"] == "MID"
    assert payload["stale_seconds"] == 195

    leg_labels = {
        leg_payload["symbol"]: leg_payload["display"]["leg_label"]
        for leg_payload in payload["legs"]
    }
    assert leg_labels["SPY 20251018P00395000"] == "SPY 395P • Oct 18 '25"
    assert leg_labels["SPY 20251018C00445000"] == "SPY 445C • Oct 18 '25"

    combo_payload_extra = result.combo_extras["combo-condor-1"]
    assert combo_payload_extra["combo_group_id"] == group.combo_group_id
    assert combo_payload_extra["label"].endswith("Credit 1.10")

    leg_extra = result.leg_extras["leg-put-short-1"]
    assert leg_extra["label"] == "SPY 395P • Oct 18 '25"


def test_combo_labels_for_various_strategies() -> None:
    # Vertical spread
    call_short = make_leg(
        leg_id="leg-call-short",
        symbol="MSFT 20240517C00320000",
        underlying="MSFT",
        expiry="2024-05-17",
        dte=30,
        right="CALL",
        strike="320",
        quantity="-1",
        avg_cost="2.20",
        mark="2.10",
        mark_source="MID",
        stale_seconds=45,
        delta="0.35",
        gamma="0.02",
        theta="-0.18",
        vega="-1.9",
    )
    call_long = make_leg(
        leg_id="leg-call-long",
        symbol="MSFT 20240517C00315000",
        underlying="MSFT",
        expiry="2024-05-17",
        dte=30,
        right="CALL",
        strike="315",
        quantity="1",
        avg_cost="1.60",
        mark="1.58",
        mark_source="MID",
        stale_seconds=45,
        delta="-0.28",
        gamma="-0.02",
        theta="0.14",
        vega="1.4",
    )
    vertical = make_combo(
        combo_id="combo-vertical",
        strategy=ComboStrategy.VERTICAL,
        underlying="MSFT",
        dte=30,
        net_price="0.60",
        delta="-7.0",
        gamma="0.6",
        theta="6.2",
        vega="-5.8",
        legs=(call_short, call_long),
    )

    # Calendar
    calendar_near = make_leg(
        leg_id="leg-cal-near",
        symbol="AAPL 20240517C00180000",
        underlying="AAPL",
        expiry="2024-05-17",
        dte=62,
        right="CALL",
        strike="180",
        quantity="-1",
        avg_cost="2.40",
        mark="2.35",
        mark_source="MID",
        stale_seconds=50,
        delta="0.42",
        gamma="0.03",
        theta="-0.22",
        vega="-3.1",
    )
    calendar_far = make_leg(
        leg_id="leg-cal-far",
        symbol="AAPL 20240719C00180000",
        underlying="AAPL",
        expiry="2024-07-19",
        dte=124,
        right="CALL",
        strike="180",
        quantity="1",
        avg_cost="4.80",
        mark="4.76",
        mark_source="LAST",
        stale_seconds=70,
        delta="-0.35",
        gamma="-0.02",
        theta="0.18",
        vega="3.9",
    )
    calendar = make_combo(
        combo_id="combo-calendar",
        strategy=ComboStrategy.CALENDAR,
        underlying="AAPL",
        dte=62,
        net_price="-2.40",
        delta="1.8",
        gamma="-0.4",
        theta="-5.2",
        vega="12.4",
        legs=(calendar_near, calendar_far),
    )

    # Straddle
    straddle_call = make_leg(
        leg_id="leg-straddle-call",
        symbol="TSLA 20240308C00240000",
        underlying="TSLA",
        expiry="2024-03-08",
        dte=7,
        right="CALL",
        strike="240",
        quantity="1",
        avg_cost="5.40",
        mark="5.32",
        mark_source="MID",
        stale_seconds=55,
        delta="0.52",
        gamma="0.05",
        theta="-0.28",
        vega="3.4",
    )
    straddle_put = make_leg(
        leg_id="leg-straddle-put",
        symbol="TSLA 20240308P00240000",
        underlying="TSLA",
        expiry="2024-03-08",
        dte=7,
        right="PUT",
        strike="240",
        quantity="1",
        avg_cost="5.20",
        mark="5.18",
        mark_source="MID",
        stale_seconds=55,
        delta="-0.48",
        gamma="0.05",
        theta="-0.26",
        vega="3.1",
    )
    straddle = make_combo(
        combo_id="combo-straddle",
        strategy=ComboStrategy.STRADDLE,
        underlying="TSLA",
        dte=7,
        net_price="-10.60",
        delta="0.4",
        gamma="1.0",
        theta="-14.2",
        vega="6.5",
        legs=(straddle_call, straddle_put),
    )

    result = group_option_combos((vertical, calendar, straddle))
    labels = {
        group.combo_group_id: group.to_payload()["label"] for group in result.groups
    }

    assert (
        labels["VERTICAL|MSFT|C:315/320@2024-05-17"]
        == "MSFT 315/320C • 30d • Credit 0.60"
    )
    assert (
        labels["CALENDAR|AAPL|C:180@2024-05-17|C:180@2024-07-19"]
        == "AAPL 180C CAL • May→Jul • Debit 2.40"
    )
    assert (
        labels["STRADDLE|TSLA|C:240@2024-03-08|P:240@2024-03-08"] == "TSLA 240C+P • 7d"
    )


def test_options_payload_exposes_group_data() -> None:
    instrument = Instrument(
        symbol="MSFT 20240517C00320000",
        instrument_type=InstrumentType.OPTION,
        multiplier=Decimal("100"),
    )
    position = Position(
        instrument=instrument,
        quantity=Decimal("-1"),
        avg_cost=Decimal("2.00"),
        metadata={
            "underlying": "MSFT",
            "expiry": "2024-05-17",
            "right": "C",
            "strike": Decimal("320"),
        },
    )
    hedge = Position(
        instrument=Instrument(
            symbol="MSFT 20240517C00315000",
            instrument_type=InstrumentType.OPTION,
            multiplier=Decimal("100"),
        ),
        quantity=Decimal("1"),
        avg_cost=Decimal("1.40"),
        metadata={
            "underlying": "MSFT",
            "expiry": "2024-05-17",
            "right": "C",
            "strike": Decimal("315"),
        },
    )
    quote_short = Quote(
        symbol=instrument.symbol,
        bid=Decimal("2.05"),
        ask=Decimal("2.15"),
        last=Decimal("2.10"),
        previous_close=Decimal("2.00"),
        session=TradingSession.RTH,
        updated_at=NOW,
    )
    quote_long = Quote(
        symbol=hedge.instrument.symbol,
        bid=Decimal("1.35"),
        ask=Decimal("1.45"),
        last=Decimal("1.40"),
        previous_close=Decimal("1.30"),
        session=TradingSession.RTH,
        updated_at=NOW,
    )

    state = PositionsState()
    state.refresh(
        positions=[position, hedge],
        quotes=[quote_short, quote_long],
        snapshot_at=NOW,
        data_source="test",
    )

    payload = state.options_payload(now=NOW)
    assert "combo_groups" in payload
    assert len(payload["combos"]) == 1
    assert len(payload["combo_groups"]) == 1

    combo = payload["combos"][0]
    assert combo["combo_group_id"] == payload["combo_groups"][0]["combo_group_id"]
    assert "label" in combo
    assert combo["label"].startswith("MSFT 315/320C")
    assert combo["legs"][0]["display"]["leg_label"].startswith("MSFT")

    group = payload["combo_groups"][0]
    assert group["group_qty"] == 1.0
    assert group["label"].startswith("MSFT 315/320C")
    assert group["legs"][0]["display"]["leg_label"].startswith("MSFT")
    assert len(payload["legs"]) == 0  # no orphan legs
