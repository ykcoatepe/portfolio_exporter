"""Registry helpers for PSD runtime components."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from typing import Any

from ..analyzers.base import Analyzer, AnalyzerFactory

_AnalyzerFactoryRecord = tuple[str, AnalyzerFactory]

_ANALYZER_FACTORIES: dict[str, _AnalyzerFactoryRecord] = {}
_LOCK = threading.Lock()


def _normalize_name(name: str) -> str:
    normalized = name.strip().lower()
    if not normalized:
        raise ValueError("Analyzer name must be a non-empty string")
    return normalized


def register_analyzer_factory(
    name: str,
    factory: AnalyzerFactory,
    *,
    replace: bool = False,
) -> None:
    """Register a factory callable that returns an ``Analyzer`` instance."""
    if not callable(factory):
        raise TypeError("Analyzer factory must be callable")
    normalized = _normalize_name(name)
    with _LOCK:
        if not replace and normalized in _ANALYZER_FACTORIES:
            raise ValueError(f"Analyzer factory '{name}' is already registered")
        _ANALYZER_FACTORIES[normalized] = (name, factory)


def get_analyzer_factory(name: str) -> AnalyzerFactory:
    """Return the registered factory for ``name``."""
    normalized = _normalize_name(name)
    with _LOCK:
        try:
            _, factory = _ANALYZER_FACTORIES[normalized]
        except KeyError as exc:
            raise KeyError(f"Analyzer factory '{name}' is not registered") from exc
        return factory


def create_analyzer(name: str, *args: Any, **kwargs: Any) -> Analyzer:
    """Instantiate an analyzer using the registered factory for ``name``."""
    factory = get_analyzer_factory(name)
    return factory(*args, **kwargs)


def iter_analyzer_factories() -> Iterable[tuple[str, AnalyzerFactory]]:
    """Yield (name, factory) pairs for registered analyzers."""
    with _LOCK:
        items = tuple(_ANALYZER_FACTORIES.values())
    yield from items


def analyzer_factory(
    name: str, *, replace: bool = False
) -> Callable[[AnalyzerFactory], AnalyzerFactory]:
    """Decorator that calls :func:`register_analyzer_factory`."""

    def wrapper(factory: AnalyzerFactory) -> AnalyzerFactory:
        register_analyzer_factory(name, factory, replace=replace)
        return factory

    return wrapper


__all__ = [
    "analyzer_factory",
    "create_analyzer",
    "get_analyzer_factory",
    "iter_analyzer_factories",
    "register_analyzer_factory",
]
