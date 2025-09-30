from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from positions_engine.combos.detector import (
    ComboDetection,
    OptionCombo,
    OptionLegSnapshot,
)
from positions_engine.combos.eval import PlaybookEvaluation, evaluate_playbook_targets
from positions_engine.combos.taxonomy import ComboStrategy
from positions_engine.core.models import Quote, TradingSession
from positions_engine.service.state import PositionsState


def _make_leg(
    *,
    leg_id: str,
    symbol: str,
    underlying: str,
    strike: str,
    right: str,
    quantity: str,
    avg_cost: str,
    expiry: str = "2025-05-16",
    dte: int = 30,
    total_pnl: str = "0",
) -> OptionLegSnapshot:
    qty = Decimal(quantity)
    avg = Decimal(avg_cost)
    multiplier = Decimal("100")
    total_basis = avg * qty * multiplier
    return OptionLegSnapshot(
        leg_id=leg_id,
        instrument_symbol=symbol,
        account="TEST",
        underlying=underlying,
        expiry=expiry,
        dte=dte,
        right=right,
        strike=Decimal(strike),
        quantity=qty,
        ratio=abs(qty) or Decimal("1"),
        multiplier=multiplier,
        avg_cost=avg,
        mark=Decimal("0"),
        mark_source="MID",
        stale_seconds=None,
        previous_close=None,
        delta=None,
        gamma=None,
        theta=None,
        vega=None,
        iv=None,
        day_pnl=Decimal("0"),
        total_pnl=Decimal(total_pnl),
        day_basis=None,
        total_basis=total_basis,
        feed_strategy_id=None,
        feed_combo_id=None,
        notes=tuple(),
    )


def _make_quote(symbol: str, value: str) -> Quote:
    now = datetime.now(tz=UTC)
    return Quote(
        symbol=symbol,
        last=Decimal(value),
        last_ts=now,
        session=TradingSession.RTH,
        updated_at=now,
    )


def test_credit_vertical_tp_flags() -> None:
    short_leg = _make_leg(
        leg_id="short-call",
        symbol="SPY 20250516C00430000",
        underlying="SPY",
        strike="430",
        right="CALL",
        quantity="-2",
        avg_cost="1.20",
    )
    long_leg = _make_leg(
        leg_id="long-call",
        symbol="SPY 20250516C00435000",
        underlying="SPY",
        strike="435",
        right="CALL",
        quantity="2",
        avg_cost="0.60",
    )
    combo = OptionCombo(
        combo_id="credit-vert",
        strategy=ComboStrategy.VERTICAL,
        account="TEST",
        underlying="SPY",
        dte=30,
        net_price=Decimal("-1.20"),
        sum_delta=Decimal("0"),
        sum_gamma=Decimal("0"),
        sum_theta=Decimal("0"),
        sum_vega=Decimal("0"),
        day_pnl=Decimal("0"),
        total_pnl=Decimal("60"),
        day_pnl_percent=None,
        total_pnl_percent=None,
        legs=(short_leg, long_leg),
        notes=tuple(),
    )

    evaluation = evaluate_playbook_targets(
        combos=[combo],
        legs=(),
        quotes={"^VIX": _make_quote("^VIX", "18")},
    )
    playbook = evaluation.combo_targets[combo.combo_id]

    assert playbook["tp_band_pct"] == [0.4, 0.6]
    assert playbook["tp_band_low_pct"] == 0.4
    assert playbook["tp_band_high_pct"] == 0.6
    assert playbook["tp_hit"] is True
    assert playbook["tp_done"] is False
    assert playbook["sl_hit"] is False
    assert playbook["next_action"] == "TRIM"
    progress = playbook["progress"]
    assert playbook["progress_pct_of_max"] == 0.5
    assert playbook["progress_pct_of_goal"] == pytest.approx(0.8333, rel=1e-3)
    assert progress["pct_of_max_profit_or_r"] == 0.5
    assert progress["pct_of_goal"] == pytest.approx(0.8333, rel=1e-3)


def test_credit_vertical_stop_hit() -> None:
    short_leg = _make_leg(
        leg_id="short",
        symbol="SPY 20250516P00400000",
        underlying="SPY",
        strike="400",
        right="PUT",
        quantity="-1",
        avg_cost="1.50",
    )
    long_leg = _make_leg(
        leg_id="long",
        symbol="SPY 20250516P00405000",
        underlying="SPY",
        strike="405",
        right="PUT",
        quantity="1",
        avg_cost="0.80",
    )
    combo = OptionCombo(
        combo_id="credit-put",
        strategy=ComboStrategy.VERTICAL,
        account="TEST",
        underlying="SPY",
        dte=25,
        net_price=Decimal("-0.70"),
        sum_delta=Decimal("0"),
        sum_gamma=Decimal("0"),
        sum_theta=Decimal("0"),
        sum_vega=Decimal("0"),
        day_pnl=Decimal("0"),
        total_pnl=Decimal("-500"),
        day_pnl_percent=None,
        total_pnl_percent=None,
        legs=(short_leg, long_leg),
        notes=tuple(),
    )

    evaluation = evaluate_playbook_targets(
        combos=[combo],
        legs=(),
        quotes={"^VIX": _make_quote("^VIX", "22")},
    )
    playbook = evaluation.combo_targets[combo.combo_id]
    assert playbook["sl_hit"] is True
    assert playbook["next_action"] == "CUT"


def test_debit_vertical_targets() -> None:
    long_leg = _make_leg(
        leg_id="long",
        symbol="QQQ 20250419C00380000",
        underlying="QQQ",
        strike="380",
        right="CALL",
        quantity="1",
        avg_cost="2.50",
    )
    short_leg = _make_leg(
        leg_id="short",
        symbol="QQQ 20250419C00390000",
        underlying="QQQ",
        strike="390",
        right="CALL",
        quantity="-1",
        avg_cost="1.50",
    )
    combo = OptionCombo(
        combo_id="debit-vert",
        strategy=ComboStrategy.VERTICAL,
        account="TEST",
        underlying="QQQ",
        dte=40,
        net_price=Decimal("1.00"),
        sum_delta=Decimal("0"),
        sum_gamma=Decimal("0"),
        sum_theta=Decimal("0"),
        sum_vega=Decimal("0"),
        day_pnl=Decimal("0"),
        total_pnl=Decimal("200"),
        day_pnl_percent=None,
        total_pnl_percent=None,
        legs=(long_leg, short_leg),
        notes=tuple(),
    )

    evaluation = evaluate_playbook_targets(
        combos=[combo],
        legs=(),
        quotes={},
    )
    playbook = evaluation.combo_targets[combo.combo_id]
    assert playbook["tp_band_pct"] == [1.0, 2.0]
    assert playbook["tp_hit"] is True
    assert playbook["tp_done"] is True
    assert playbook["sl_hit"] is False
    assert playbook["next_action"] == "TAKE_PROFIT"
    progress = playbook["progress"]
    assert progress["pct_of_max_profit_or_r"] == 2.0
    assert progress["pct_of_goal"] == 1.0


def test_single_short_leg_uses_credit_band() -> None:
    short_leg = _make_leg(
        leg_id="short-leg",
        symbol="AAPL 20250321P00180000",
        underlying="AAPL",
        strike="180",
        right="PUT",
        quantity="-3",
        avg_cost="1.20",
        total_pnl="200",
    )

    evaluation = evaluate_playbook_targets(
        combos=(),
        legs=[short_leg],
        quotes={"^VIX": _make_quote("^VIX", "13.5")},
    )
    playbook = evaluation.leg_targets[short_leg.leg_id]
    assert playbook["tp_band_pct"] == [0.5, 0.7]
    assert playbook["tp_band_low_pct"] == 0.5
    assert playbook["tp_band_high_pct"] == 0.7
    assert playbook["tp_hit"] is True
    assert playbook["tp_done"] is False
    assert playbook["next_action"] == "TRIM"


def test_options_payload_includes_playbook_fields() -> None:
    short_leg = _make_leg(
        leg_id="credit-short",
        symbol="SPY 20250516C00420000",
        underlying="SPY",
        strike="420",
        right="CALL",
        quantity="-1",
        avg_cost="1.10",
    )
    long_leg = _make_leg(
        leg_id="credit-long",
        symbol="SPY 20250516C00425000",
        underlying="SPY",
        strike="425",
        right="CALL",
        quantity="1",
        avg_cost="0.55",
    )
    combo = OptionCombo(
        combo_id="psd-credit",
        strategy=ComboStrategy.VERTICAL,
        account="TEST",
        underlying="SPY",
        dte=28,
        net_price=Decimal("-0.55"),
        sum_delta=Decimal("0"),
        sum_gamma=Decimal("0"),
        sum_theta=Decimal("0"),
        sum_vega=Decimal("0"),
        day_pnl=Decimal("0"),
        total_pnl=Decimal("40"),
        day_pnl_percent=None,
        total_pnl_percent=None,
        legs=(short_leg, long_leg),
        notes=tuple(),
    )

    detection = ComboDetection(combos=(combo,), orphans=(short_leg,), detection_ms=0.0)
    state = PositionsState()
    now = datetime(2025, 3, 14, tzinfo=UTC)
    state._options_cache = {
        "positions_version": state._positions_version,
        "quotes_version": state._quotes_version,
        "day": now.date(),
        "detection": detection,
    }
    state._quotes = {"^VIX": _make_quote("^VIX", "20")}

    payload = state.options_payload(now=now)
    combo_payload = payload["combos"][0]
    assert combo_payload["tp_band_pct"] == [0.4, 0.6]
    assert combo_payload["tp_band_low_pct"] == 0.4
    assert combo_payload["tp_band_high_pct"] == 0.6
    assert "progress" in combo_payload
    assert combo_payload["progress_pct_of_goal"] is None or isinstance(
        combo_payload["progress_pct_of_goal"], float
    )
    assert "playbook" in payload
    leg_payload = payload["legs"][0]
    assert leg_payload["tp_band_pct"] == [0.4, 0.6]
    assert leg_payload["tp_band_low_pct"] == 0.4
    assert leg_payload["tp_band_high_pct"] == 0.6


def test_combo_group_merges_playbook_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    short_leg_one = _make_leg(
        leg_id="group-short-1",
        symbol="SPY 20250620C00420000",
        underlying="SPY",
        strike="420",
        right="CALL",
        quantity="-1",
        avg_cost="1.00",
    )
    long_leg_one = _make_leg(
        leg_id="group-long-1",
        symbol="SPY 20250620C00425000",
        underlying="SPY",
        strike="425",
        right="CALL",
        quantity="1",
        avg_cost="0.50",
    )
    combo_one = OptionCombo(
        combo_id="group-combo-1",
        strategy=ComboStrategy.VERTICAL,
        account="TEST",
        underlying="SPY",
        dte=35,
        net_price=Decimal("-0.50"),
        sum_delta=Decimal("0"),
        sum_gamma=Decimal("0"),
        sum_theta=Decimal("0"),
        sum_vega=Decimal("0"),
        day_pnl=Decimal("0"),
        total_pnl=Decimal("40"),
        day_pnl_percent=None,
        total_pnl_percent=None,
        legs=(short_leg_one, long_leg_one),
        notes=tuple(),
    )

    short_leg_two = _make_leg(
        leg_id="group-short-2",
        symbol="SPY 20250620C00420001",
        underlying="SPY",
        strike="420",
        right="CALL",
        quantity="-1",
        avg_cost="1.05",
    )
    long_leg_two = _make_leg(
        leg_id="group-long-2",
        symbol="SPY 20250620C00425001",
        underlying="SPY",
        strike="425",
        right="CALL",
        quantity="1",
        avg_cost="0.55",
    )
    combo_two = OptionCombo(
        combo_id="group-combo-2",
        strategy=ComboStrategy.VERTICAL,
        account="TEST",
        underlying="SPY",
        dte=35,
        net_price=Decimal("-0.60"),
        sum_delta=Decimal("0"),
        sum_gamma=Decimal("0"),
        sum_theta=Decimal("0"),
        sum_vega=Decimal("0"),
        day_pnl=Decimal("0"),
        total_pnl=Decimal("90"),
        day_pnl_percent=None,
        total_pnl_percent=None,
        legs=(short_leg_two, long_leg_two),
        notes=tuple(),
    )

    combo_targets = {
        combo_one.combo_id: {
            "tp_band_pct": [0.25, 0.5],
            "tp_band_low_pct": 0.25,
            "tp_band_high_pct": 0.5,
            "tp_hit": True,
            "tp_done": False,
            "sl_hit": False,
            "sl_r": 1.0,
            "next_action": "TRIM",
            "progress_pct_of_goal": 0.5,
            "progress_pct_of_max": 0.3,
            "progress": {
                "pct_of_goal": 0.5,
                "pct_of_max_profit_or_r": 0.3,
            },
            "exit_as_unit": False,
        },
        combo_two.combo_id: {
            "tp_band_pct": [0.25, 0.5],
            "tp_hit": True,
            "tp_done": True,
            "sl_hit": False,
            "sl_r": None,
            "next_action": "TAKE_PROFIT",
            "progress_pct_of_goal": 1.1,
            "progress_pct_of_max": 0.8,
            "progress": {
                "pct_of_goal": 1.1,
                "pct_of_max_profit_or_r": 0.8,
            },
            "exit_as_unit": True,
        },
    }

    def _fake_evaluation(*_: object) -> PlaybookEvaluation:
        return PlaybookEvaluation(combo_targets=combo_targets, leg_targets={}, meta={})

    monkeypatch.setattr(
        "positions_engine.service.state.evaluate_playbook_targets",
        _fake_evaluation,
    )

    detection = ComboDetection(
        combos=(combo_one, combo_two), orphans=(), detection_ms=0.0
    )
    state = PositionsState()
    now = datetime(2025, 5, 1, tzinfo=UTC)
    state._options_cache = {
        "positions_version": state._positions_version,
        "quotes_version": state._quotes_version,
        "day": now.date(),
        "detection": detection,
    }

    payload = state.options_payload(now=now)
    combo_groups = payload["combo_groups"]
    assert len(combo_groups) == 1
    group_payload = combo_groups[0]
    assert group_payload["tp_band_pct"] == [0.25, 0.5]
    assert group_payload["tp_band_low_pct"] == 0.25
    assert group_payload["tp_band_high_pct"] == 0.5
    assert group_payload["tp_hit"] is True
    assert group_payload["tp_done"] is True
    assert group_payload["sl_hit"] is False
    assert group_payload["sl_r"] == pytest.approx(1.0)
    assert group_payload["next_action"] == "TRIM"
    assert group_payload["exit_as_unit"] is True
    assert group_payload["progress_pct_of_goal"] == pytest.approx(0.8)
    assert group_payload["progress_pct_of_max"] == pytest.approx(0.55)
    assert group_payload["progress"]["pct_of_goal"] == pytest.approx(0.8)
    assert group_payload["progress"]["pct_of_max_profit_or_r"] == pytest.approx(0.55)
