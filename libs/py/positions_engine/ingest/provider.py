# SPDX-License-Identifier: MIT

"""Provider registry for the positions engine ingest layer."""

from __future__ import annotations

import logging
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

from .csv import CsvLoadResult, load_csv_records
from .demo import load_demo_dataset
from .internal import InternalScriptsProvider

logger = logging.getLogger(__name__)


class Provider(Protocol):
    """Lightweight loader protocol returning normalized records."""

    name: str

    def load(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return ``(positions, quotes)`` lists."""


class CsvProvider:
    """Adapter around :func:`load_csv_records`."""

    name = "csv"

    def __init__(self, base_dir: Path | str) -> None:
        self._base_dir = Path(base_dir).expanduser()
        self.metadata: dict[str, Any] | None = None

    def load(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        result: CsvLoadResult = load_csv_records(self._base_dir)
        self.metadata = result.metadata
        return result.positions, result.quotes


class DemoProvider:
    """Load the bundled demo dataset for development use."""

    name = "demo"

    def load(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        positions, quotes = load_demo_dataset()
        return positions, quotes


_LAST_PROVIDER_INFO: dict[str, Any] | None = None


def last_provider_info() -> dict[str, Any] | None:
    """Return details captured during the last :func:`choose_provider` call."""

    return _LAST_PROVIDER_INFO


def choose_provider(data_root: Path | str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """Return the first provider that yields data, respecting built-in precedence."""

    global _LAST_PROVIDER_INFO

    allow_empty = os.getenv("POSITIONS_ENGINE_ALLOW_EMPTY", "0") == "1"
    demo_env_enabled = os.getenv("POSITIONS_ENGINE_DEMO", "0") == "1"
    include_demo = demo_env_enabled or not allow_empty

    providers: list[Provider] = [InternalScriptsProvider(), CsvProvider(data_root)]
    if include_demo:
        providers.append(DemoProvider())

    _LAST_PROVIDER_INFO = None

    for provider in providers:
        try:
            positions, quotes = provider.load()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.info("Ingest provider %s failed: %s", provider.name, exc)
            continue
        if positions or quotes:
            info: dict[str, Any] = {"name": provider.name}
            detail = getattr(provider, "source_detail", None)
            if detail:
                info["detail"] = detail
            metadata = getattr(provider, "metadata", None)
            if metadata:
                info["metadata"] = metadata
            positions_view = getattr(provider, "positions_view", None)
            if positions_view is not None:
                info["positions_view"] = deepcopy(positions_view)
            _LAST_PROVIDER_INFO = info
            return positions, quotes, provider.name

    return [], [], None
