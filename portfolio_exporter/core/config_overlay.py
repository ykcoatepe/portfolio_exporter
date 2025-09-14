from __future__ import annotations

import os
from typing import Any, Dict, Optional


def _env_bool(name: str, default: Optional[bool] = None) -> Optional[bool]:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: Optional[int] = None) -> Optional[int]:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return int(v)
    except Exception:
        return default


def overlay_sentinel(base: Dict[str, Any], memory: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build effective sentinel config.

    Precedence (highest to lowest):
    - CLI (handled by argparse outside of this function)
    - ENV (MOMO_SEN_*)
    - MEMORY (.codex/memory.json preferences.sentinel.*)
    - FILE (base)
    - DEFAULTS (present in base before overlay)
    """
    eff = dict(base)

    # 1) MEMORY overlay
    mem = memory or {}
    if "allow_afternoon_rearm" in mem:
        eff["allow_afternoon_rearm"] = bool(mem["allow_afternoon_rearm"])
    if "halt_rearm" in mem:
        eff["halt_rearm"] = bool(mem["halt_rearm"])
    if "cooldown_bars" in mem:
        try:
            eff["cooldown_bars"] = int(mem["cooldown_bars"])
        except Exception:
            pass
    if "require_vwap_recross" in mem:
        eff["require_vwap_recross"] = bool(mem["require_vwap_recross"])
    if "et_afternoon_rearm" in mem:
        eff["et_afternoon_rearm"] = str(mem["et_afternoon_rearm"])
    if "et_no_new_signals_after" in mem:
        eff["et_no_new_signals_after"] = str(mem["et_no_new_signals_after"])
    if "halt_mini_orb_minutes" in mem:
        try:
            eff["halt_mini_orb_minutes"] = int(mem["halt_mini_orb_minutes"])
        except Exception:
            pass
    if "halt_rearm_grace_sec" in mem:
        try:
            eff["halt_rearm_grace_sec"] = int(mem["halt_rearm_grace_sec"])
        except Exception:
            pass
    if "max_halts_per_day" in mem:
        try:
            eff["max_halts_per_day"] = int(mem["max_halts_per_day"])
        except Exception:
            pass

    # 2) ENV overlay
    b = _env_bool("MOMO_SEN_ALLOW_AFTERNOON_REARM")
    eff["allow_afternoon_rearm"] = eff.get("allow_afternoon_rearm") if b is None else b
    b = _env_bool("MOMO_SEN_HALT_REARM")
    eff["halt_rearm"] = eff.get("halt_rearm") if b is None else b
    i = _env_int("MOMO_SEN_COOLDOWN_BARS")
    eff["cooldown_bars"] = eff.get("cooldown_bars", 10) if i is None else i
    b = _env_bool("MOMO_SEN_REQUIRE_VWAP_RECROSS")
    eff["require_vwap_recross"] = eff.get("require_vwap_recross") if b is None else b
    s = os.getenv("MOMO_SEN_ET_AFTERNOON_REARM")
    eff["et_afternoon_rearm"] = eff.get("et_afternoon_rearm", "13:30") if not s else s
    s = os.getenv("MOMO_SEN_ET_NO_NEW_AFTER")
    eff["et_no_new_signals_after"] = eff.get("et_no_new_signals_after", "15:30") if not s else s
    i = _env_int("MOMO_SEN_HALT_MINI_ORB_MINUTES")
    eff["halt_mini_orb_minutes"] = eff.get("halt_mini_orb_minutes", 3) if i is None else i
    i = _env_int("MOMO_SEN_HALT_REARM_GRACE_SEC")
    eff["halt_rearm_grace_sec"] = eff.get("halt_rearm_grace_sec", 45) if i is None else i
    i = _env_int("MOMO_SEN_MAX_HALTS_PER_DAY")
    eff["max_halts_per_day"] = eff.get("max_halts_per_day", 1) if i is None else i

    return eff
