"""Environment-driven feature flag helpers for PSD components."""

from __future__ import annotations

import os
from typing import Final

_TRUE_VALUES: Final = {"1", "true", "yes", "on"}
_FALSE_VALUES: Final = {"0", "false", "no", "off"}


class Flags:
    """Utility helpers for checking feature flags."""

    @staticmethod
    def enabled(name: str, default: bool = False) -> bool:
        """Return True when the environment flag resolves to an enabled value."""
        value = os.getenv(name, "").strip().lower()
        if value in _TRUE_VALUES:
            return True
        if value in _FALSE_VALUES:
            return False
        return default
