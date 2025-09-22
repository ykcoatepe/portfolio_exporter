"""Lightweight analyzer contracts used by the PSD runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class Signal:
    """Atomic analyzer output describing an actionable condition."""

    name: str
    value: Any
    score: float | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Candidate:
    """Input payload handed to analyzers for evaluation."""

    identifier: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    context: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AnalyzerResult:
    """Structured response produced by an analyzer."""

    signals: tuple[Signal, ...] = field(default_factory=tuple)
    notes: Mapping[str, Any] | None = None

    def has_signals(self) -> bool:
        """Return True when the analyzer produced at least one signal."""
        return len(self.signals) > 0


@runtime_checkable
class Analyzer(Protocol):
    """Protocol that PSD analyzers must implement."""

    name: str

    def analyze(self, candidate: Candidate) -> AnalyzerResult | None:
        """Evaluate *candidate* and return analyzer output when applicable."""


AnalyzerFactory = Callable[..., Analyzer]

__all__ = [
    "Analyzer",
    "AnalyzerFactory",
    "AnalyzerResult",
    "Candidate",
    "Signal",
]
