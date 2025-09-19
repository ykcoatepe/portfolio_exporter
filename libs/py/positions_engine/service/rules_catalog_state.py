# SPDX-License-Identifier: MIT

"""In-memory state and helpers for the live rules catalog service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from ..rules import Rule
from ..rules.catalog import (
    CATALOG_PATH,
    CatalogError,
    CatalogValidationError,
    RulesCatalog,
    RulesCatalogDraft,
    atomic_write,
    dump_catalog,
    load_catalog,
    parse_catalog,
    rules_to_dict,
)
from ..rules.eval import RuleEvaluationError, RuleParseError
from .rules_state import RulesState
from .state import PositionsState


@dataclass(slots=True)
class CatalogValidationResult:
    ok: bool
    counters: dict[str, int]
    top: list[dict[str, Any]]
    errors: list[str]
    rules: list[Rule]


class RulesCatalogState:
    """Coordinates catalog persistence, validation, and publication workflows."""

    def __init__(
        self,
        positions_state: PositionsState,
        rules_state: RulesState,
        *,
        path: Path = CATALOG_PATH,
    ) -> None:
        self._positions_state = positions_state
        self._rules_state = rules_state
        self._path = path
        self._yaml_error: CatalogError | None = None
        self._catalog = self._load_or_default()

    @property
    def catalog(self) -> RulesCatalog:
        return self._catalog

    @property
    def rules(self) -> list[Rule]:
        return list(self._catalog.rules)

    def validate_catalog_text(self, text: str) -> CatalogValidationResult:
        if self._yaml_error is not None:
            message = str(self._yaml_error)
            return CatalogValidationResult(
                ok=False, counters={}, top=[], errors=[message], rules=[]
            )

        errors: list[str] = []
        try:
            draft = parse_catalog(text)
        except (CatalogValidationError, CatalogError) as exc:
            errors.append(str(exc))
            return CatalogValidationResult(
                ok=False, counters={}, top=[], errors=errors, rules=[]
            )

        try:
            summary, _evaluation = self._summary_for_rules(draft.rules)
        except (RuleParseError, RuleEvaluationError) as exc:
            errors.append(str(exc))
            return CatalogValidationResult(
                ok=False, counters={}, top=[], errors=errors, rules=draft.rules
            )

        counters = _normalize_counters(summary.get("breaches", {}))
        top = summary.get("top", []) if isinstance(summary, dict) else []
        return CatalogValidationResult(
            ok=True,
            counters=counters,
            top=top if isinstance(top, list) else [],
            errors=errors,
            rules=draft.rules,
        )

    def preview_catalog(self, text: str) -> tuple[CatalogValidationResult, dict[str, Any]]:
        validation = self.validate_catalog_text(text)
        if not validation.ok:
            return validation, {"added": [], "removed": [], "changed": []}
        diff = _diff_rules(self._catalog.rules, validation.rules)
        return validation, diff

    def publish_catalog(self, text: str, author: str | None = None) -> RulesCatalog:
        if self._yaml_error is not None:
            raise CatalogError(str(self._yaml_error)) from self._yaml_error

        validation = self.validate_catalog_text(text)
        if not validation.ok:
            message = ", ".join(validation.errors) or "Catalog validation failed"
            raise CatalogValidationError(message)

        next_version = (self._catalog.version or 0) + 1
        catalog = RulesCatalog(
            version=next_version,
            updated_at=datetime.now(tz=UTC),
            updated_by=author,
            rules=validation.rules,
        )
        yaml_text = dump_catalog(catalog)
        atomic_write(yaml_text, path=self._path)
        self._catalog = catalog
        self._rules_state.set_rules(catalog.rules)
        return catalog

    def reload(self) -> RulesCatalog:
        self._catalog = self._load_or_default()
        return self._catalog

    def as_dict(self) -> dict[str, Any]:
        catalog = self._catalog
        return {
            "version": catalog.version,
            "updated_at": catalog.updated_at.isoformat(),
            "updated_by": catalog.updated_by,
            "rules": rules_to_dict(catalog.rules),
        }

    def _summary_for_rules(self, rules: Iterable[Rule]) -> tuple[dict[str, Any], Any]:
        temp_state = RulesState(self._positions_state, rules=rules)
        return temp_state.summary()

    def _load_or_default(self) -> RulesCatalog:
        try:
            catalog = load_catalog(self._path)
        except CatalogError as exc:
            self._yaml_error = exc
            fallback_rules = list(self._rules_state.rules)
            return RulesCatalog(rules=fallback_rules)
        else:
            self._yaml_error = None

        if catalog.rules:
            self._rules_state.set_rules(catalog.rules)
            return catalog
        # no stored rules; fall back to in-memory defaults without resetting
        fallback_rules = list(self._rules_state.rules)
        return RulesCatalog(
            version=catalog.version,
            updated_at=catalog.updated_at,
            updated_by=catalog.updated_by,
            rules=fallback_rules,
        )


def _normalize_counters(raw: dict[str, Any]) -> dict[str, int]:
    counters = {"critical": 0, "warning": 0, "info": 0}
    for key in counters:
        value = raw.get(key) if isinstance(raw, dict) else 0
        counters[key] = int(value or 0)
    counters["total"] = sum(counters.values())
    return counters


def _diff_rules(current: Iterable[Rule], proposed: Iterable[Rule]) -> dict[str, Any]:
    current_by_id = {rule.rule_id: rule for rule in current}
    proposed_by_id = {rule.rule_id: rule for rule in proposed}

    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []

    for rule_id, rule in proposed_by_id.items():
        if rule_id not in current_by_id:
            added.append(rule.model_dump(mode="json"))
            continue
        previous = current_by_id[rule_id].model_dump(mode="json")
        current_dump = rule.model_dump(mode="json")
        delta: dict[str, dict[str, Any]] = {}
        for field, new_value in current_dump.items():
            old_value = previous.get(field)
            if old_value != new_value:
                delta[field] = {"old": old_value, "new": new_value}
        if delta:
            changed.append({"rule_id": rule_id, "changes": delta})

    for rule_id, rule in current_by_id.items():
        if rule_id not in proposed_by_id:
            removed.append(rule.model_dump(mode="json"))

    return {"added": added, "removed": removed, "changed": changed}
