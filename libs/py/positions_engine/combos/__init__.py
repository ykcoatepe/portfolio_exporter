# SPDX-License-Identifier: MIT

"""Option combo detection package."""

from .detector import (
    ComboDetection,
    OptionCombo,
    OptionLegSnapshot,
    build_option_leg_snapshot,
    detect_option_combos,
)
from .grouping import (
    ComboDisplay,
    ComboGroup,
    GroupingResult,
    build_combo_display,
    build_combo_group_id,
    build_leg_display,
    format_combo_label,
    format_expiry_short,
    format_month_short,
    group_option_combos,
)
from .taxonomy import ComboStrategy, strategy_label

__all__ = [
    "ComboDetection",
    "ComboStrategy",
    "ComboDisplay",
    "ComboGroup",
    "GroupingResult",
    "OptionCombo",
    "OptionLegSnapshot",
    "build_combo_display",
    "build_combo_group_id",
    "build_leg_display",
    "build_option_leg_snapshot",
    "detect_option_combos",
    "format_combo_label",
    "format_expiry_short",
    "format_month_short",
    "group_option_combos",
    "strategy_label",
]
