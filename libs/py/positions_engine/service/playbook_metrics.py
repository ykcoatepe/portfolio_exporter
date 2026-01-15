# SPDX-License-Identifier: MIT

"""Playbook v4 metrics computation and state machine for rules evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

# V/VIX cap table per VIX band (USD per point per $1M NAV)
_VVIX_CAPS_PER_1M: dict[tuple[float, float], float] = {
    (0.0, 15.0): 1500.0,
    (15.0, 20.0): 1000.0,
    (20.0, 30.0): 600.0,
    (30.0, float("inf")): 300.0,
}

_SESSION_TZ = ZoneInfo("America/New_York")


@dataclass
class HysteresisState:
    """Tracks risk state transitions with 3-session hysteresis."""

    risk_state: str = "ON"  # ON | NEUTRAL | OFF
    sessions_in_state: int = 0
    pending_transition: str | None = None
    pending_sessions: int = 0
    last_updated: datetime | None = None


# Module-level singleton (resets on restart)
_HYSTERESIS_STATE = HysteresisState()
_HYSTERESIS_THRESHOLD = 3  # sessions required for transition


def _session_key(as_of: datetime) -> date:
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)
    return as_of.astimezone(_SESSION_TZ).date()


def _evaluate_risk_transition(
    current_state: str,
    vix: float,
    vx1_gt_vx2: bool,
    spx_return_pct: float,
    pulse: float = 3.0,
) -> str | None:
    """Determine target state based on Playbook v4 §4 transitions.

    ON → Neutral: VIX > 20 or Pulse < 2
    Neutral → OFF: VIX > 30 or (VX1 > VX2 & SPX < 0)
    OFF → Neutral: VIX < 25 & contango (2d)
    Neutral → ON: VIX < 18 & Pulse >= 3 (2d)
    """
    if current_state == "ON":
        if vix > 20 or pulse < 2:
            return "NEUTRAL"
    elif current_state == "NEUTRAL":
        if vix > 30 or (vx1_gt_vx2 and spx_return_pct < 0):
            return "OFF"
        if vix < 18 and pulse >= 3:
            return "ON"
    elif current_state == "OFF":
        if vix < 25 and not vx1_gt_vx2:  # contango = VX1 < VX2
            return "NEUTRAL"
    return None


def evaluate_hysteresis(
    vix: float,
    vx1_gt_vx2: bool,
    spx_return_pct: float,
    pulse: float = 3.0,
    as_of: datetime | None = None,
) -> str:
    """Apply state machine with 3-session hysteresis. Returns current risk_state.

    Session counting advances once per NY trading date. Use ``as_of`` to pass an
    explicit timestamp when evaluating historical snapshots or tests.
    """
    global _HYSTERESIS_STATE

    now = as_of or datetime.now(tz=UTC)
    last_updated = _HYSTERESIS_STATE.last_updated
    is_new_session = last_updated is None or _session_key(now) != _session_key(
        last_updated
    )

    target = _evaluate_risk_transition(
        _HYSTERESIS_STATE.risk_state, vix, vx1_gt_vx2, spx_return_pct, pulse
    )

    if target is None:
        # No transition signal; reset pending
        _HYSTERESIS_STATE.pending_transition = None
        _HYSTERESIS_STATE.pending_sessions = 0
    elif target == _HYSTERESIS_STATE.pending_transition:
        # Same target; increment counter once per session
        if is_new_session:
            _HYSTERESIS_STATE.pending_sessions += 1
        if _HYSTERESIS_STATE.pending_sessions >= _HYSTERESIS_THRESHOLD:
            _HYSTERESIS_STATE.risk_state = target
            _HYSTERESIS_STATE.sessions_in_state = 0
            _HYSTERESIS_STATE.pending_transition = None
            _HYSTERESIS_STATE.pending_sessions = 0
    else:
        # New target; start pending (count only if session advanced)
        _HYSTERESIS_STATE.pending_transition = target
        _HYSTERESIS_STATE.pending_sessions = 1 if is_new_session else 0

    if is_new_session:
        _HYSTERESIS_STATE.sessions_in_state += 1
    _HYSTERESIS_STATE.last_updated = now
    return _HYSTERESIS_STATE.risk_state


def reset_hysteresis(state: str = "ON") -> None:
    """Reset hysteresis state (for testing)."""
    global _HYSTERESIS_STATE
    _HYSTERESIS_STATE = HysteresisState(risk_state=state)


@dataclass
class PlaybookMetrics:
    """Computed Playbook v4 metrics for rule evaluation context."""

    nav_ref: float = 206000.0
    vix: float | None = None
    vvix: float | None = None
    vx1: float | None = None
    vx2: float | None = None
    vx1_gt_vx2: bool = False
    net_vega: float = 0.0
    v_vix_ratio: float = 0.0
    v_vix_cap: float = 1000.0
    v_vix_utilization_pct: float = 0.0
    risk_state: str = "ON"
    theta_nav_pct: float = 0.0
    theta_cap_nav_pct: float = 0.10
    spx_return_pct: float = 0.0
    theta_adds_blocked: bool = False
    ptcs_score: int = 90
    journal_pct: float = 95.0
    # Data availability flags
    vix_available: bool = False
    vvix_available: bool = False
    vx_term_available: bool = False

    @classmethod
    def from_powerlaw(
        cls,
        powerlaw: dict[str, Any] | None,
        net_vega: float = 0.0,
        nav_ref: float = 206000.0,
        net_theta: float = 0.0,
        as_of: datetime | None = None,
    ) -> PlaybookMetrics:
        """Build metrics from powerlaw snapshot signals.

        Expected powerlaw structure:
        {
            "signals": {
                "vix": float,
                "vvix": float,
                "vx1": float,
                "vx2": float,
                "spx_return": float,
                ...
            }
        }

        Use ``as_of`` to keep hysteresis evaluation aligned with the caller's
        evaluation timestamp (e.g., deterministic rule summaries).
        """
        metrics = cls(nav_ref=nav_ref, net_vega=net_vega)

        signals: dict[str, Any] = {}
        if isinstance(powerlaw, dict):
            candidate = powerlaw.get("signals") or powerlaw
            if isinstance(candidate, dict):
                signals = candidate

        # Extract VIX data (support multiple key names)
        vix_raw = signals.get("vix")
        if vix_raw is None:
            vix_raw = signals.get("vix_spot")
        if vix_raw is not None:
            try:
                metrics.vix = float(vix_raw)
                metrics.vix_available = True
            except (TypeError, ValueError):
                pass

        # Extract VVIX
        vvix_raw = signals.get("vvix")
        if vvix_raw is None:
            vvix_raw = signals.get("vvix_spot")
        if vvix_raw is not None:
            try:
                metrics.vvix = float(vvix_raw)
                metrics.vvix_available = True
            except (TypeError, ValueError):
                pass

        # Extract VX term structure
        vx1_raw = signals.get("vx1")
        if vx1_raw is None:
            vx1_raw = signals.get("vx1_spot")
        vx2_raw = signals.get("vx2")
        if vx2_raw is None:
            vx2_raw = signals.get("vx2_spot")
        if vx1_raw is not None and vx2_raw is not None:
            try:
                metrics.vx1 = float(vx1_raw)
                metrics.vx2 = float(vx2_raw)
                metrics.vx1_gt_vx2 = metrics.vx1 > metrics.vx2
                metrics.vx_term_available = True
            except (TypeError, ValueError):
                pass

        # Extract SPX return
        spx_raw = (
            signals.get("spx_return")
            or signals.get("spx_return_pct")
            or signals.get("spx_ret")
        )
        if spx_raw is not None:
            try:
                metrics.spx_return_pct = float(spx_raw)
            except (TypeError, ValueError):
                pass

        # Compute V/VIX metrics (only when VIX is available)
        if metrics.vix is not None and metrics.vix > 0:
            metrics.v_vix_ratio = abs(net_vega) / metrics.vix
            vvix_for_cap = metrics.vvix if metrics.vvix is not None else 0.0
            metrics.v_vix_cap = _compute_v_vix_cap(
                metrics.vix, nav_ref, metrics.vx1_gt_vx2, vvix_for_cap
            )
            if metrics.v_vix_cap > 0:
                metrics.v_vix_utilization_pct = (
                    metrics.v_vix_ratio / metrics.v_vix_cap
                ) * 100.0
            else:
                metrics.v_vix_utilization_pct = 0.0
        else:
            metrics.v_vix_ratio = 0.0
            metrics.v_vix_cap = 0.0
            metrics.v_vix_utilization_pct = 0.0

        # Compute risk state with hysteresis when VIX is available
        if metrics.vix is not None:
            metrics.risk_state = evaluate_hysteresis(
                metrics.vix,
                metrics.vx1_gt_vx2,
                metrics.spx_return_pct,
                as_of=as_of,
            )

        # θ metrics
        if nav_ref > 0:
            metrics.theta_nav_pct = (net_theta / nav_ref) * 100.0

        # θ adds blocked if VIX >= 30 or risk_state OFF
        if metrics.vix is not None:
            metrics.theta_adds_blocked = metrics.vix >= 30 or metrics.risk_state == "OFF"
        else:
            metrics.theta_adds_blocked = metrics.risk_state == "OFF"

        return metrics

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for injection into rule evaluation context."""
        return {
            "nav_ref": self.nav_ref,
            "vix": self.vix,
            "vvix": self.vvix,
            "vx1": self.vx1,
            "vx2": self.vx2,
            "vx1_gt_vx2": self.vx1_gt_vx2,
            "net_vega": self.net_vega,
            "v_vix_ratio": self.v_vix_ratio,
            "v_vix_cap": self.v_vix_cap,
            "v_vix_utilization_pct": self.v_vix_utilization_pct,
            "risk_state": self.risk_state,
            "theta_nav_pct": self.theta_nav_pct,
            "theta_cap_nav_pct": self.theta_cap_nav_pct,
            "spx_return_pct": self.spx_return_pct,
            "theta_adds_blocked": self.theta_adds_blocked,
            "ptcs_score": self.ptcs_score,
            "journal_pct": self.journal_pct,
            "vix_available": self.vix_available,
            "vvix_available": self.vvix_available,
            "vx_term_available": self.vx_term_available,
        }


def _compute_v_vix_cap(
    vix: float, nav_ref: float, vx1_gt_vx2: bool, vvix: float
) -> float:
    """Compute V/VIX cap with NAV scaling and backwardation/VVIX penalties.

    Cap per regime (USD / pt per $1M NAV):
    VIX < 15:   1500
    15-20:      1000
    20-30:      600
    >= 30:      300

    Penalties:
    - VX1 > VX2 (backwardation): -20%
    - VVIX >= 110: -10% extra
    """
    # Find base cap for VIX band
    base_cap = 1000.0  # default
    for (low, high), cap in _VVIX_CAPS_PER_1M.items():
        if low <= vix < high:
            base_cap = cap
            break

    # Scale by NAV
    nav_scale = nav_ref / 1_000_000.0
    scaled_cap = base_cap * nav_scale

    # Apply penalties
    if vx1_gt_vx2:
        scaled_cap *= 0.80  # -20%
    if vvix >= 110:
        scaled_cap *= 0.90  # -10% extra

    return scaled_cap
