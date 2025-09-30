"""Minimal smoke tests for the PSD analyzer contracts."""

from __future__ import annotations

from psd.analyzers.base import Analyzer, AnalyzerResult, Candidate, Signal
from psd.runtime.registry import (
    analyzer_factory,
    create_analyzer,
    iter_analyzer_factories,
    register_analyzer_factory,
)


def test_analyzer_protocol_is_runtime_checkable() -> None:
    class DummyAnalyzer:
        name = "dummy"

        def analyze(
            self, candidate: Candidate
        ) -> AnalyzerResult | None:  # pragma: no cover - simple stub
            return AnalyzerResult(signals=(Signal(name="dummy", value=True),))

    instance = DummyAnalyzer()
    assert isinstance(instance, Analyzer)
    result = instance.analyze(Candidate(identifier="unit", payload={}))
    assert result is not None
    assert result.has_signals()


def test_registry_registers_factories_and_creates_instances() -> None:
    class DummyAnalyzer:
        name = "registry-dummy"

        def __init__(self, *, flag: bool = False) -> None:
            self.flag = flag

        def analyze(
            self, candidate: Candidate
        ) -> AnalyzerResult | None:  # pragma: no cover - trivial path
            if not self.flag:
                return None
            return AnalyzerResult(signals=(Signal(name="registry", value=True),))

    register_analyzer_factory(
        "contract/dummy", lambda flag=False: DummyAnalyzer(flag=flag), replace=True
    )

    instance = create_analyzer("contract/dummy", flag=True)
    assert isinstance(instance, DummyAnalyzer)
    result = instance.analyze(Candidate(identifier="unit", payload={}))
    assert isinstance(result, AnalyzerResult)

    names = {name for name, _ in iter_analyzer_factories()}
    assert "contract/dummy" in names


def test_analyzer_factory_decorator_registers_callable() -> None:
    @analyzer_factory("contract/decorated", replace=True)
    def _factory() -> Analyzer:
        class DecoratedAnalyzer:
            name = "decorated"

            def analyze(
                self, candidate: Candidate
            ) -> AnalyzerResult | None:  # pragma: no cover - trivial path
                return AnalyzerResult()

        return DecoratedAnalyzer()

    instance = create_analyzer("contract/decorated")
    assert isinstance(instance, Analyzer)
