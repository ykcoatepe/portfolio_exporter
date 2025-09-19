# SPDX-License-Identifier: MIT

"""Persistent rules catalog storage helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

try:
    import yaml  # type: ignore[import]
except ModuleNotFoundError as _yaml_import_error:  # pragma: no cover - optional dep
    yaml = None  # type: ignore[assignment]
else:  # pragma: no cover - exercised when dependency present
    _yaml_import_error = None

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .schema import Rule

CATALOG_PATH = Path("libs/py/positions_engine/rules/catalog.yaml")


class CatalogError(RuntimeError):
    """Base error for catalog persistence failures."""


class CatalogValidationError(CatalogError):
    """Raised when catalog content cannot be validated."""


def _now() -> datetime:
    return datetime.now(tz=UTC)


class RulesCatalog(BaseModel):
    """Materialized rules catalog as stored on disk."""

    version: int = Field(default=0, ge=0)
    updated_at: datetime = Field(default_factory=_now)
    updated_by: str | None = None
    rules: list[Rule] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RulesCatalogDraft(BaseModel):
    """Draft catalog parsed from YAML payloads before publish."""

    rules: list[Rule] = Field(default_factory=list)
    version: int | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None

    model_config = ConfigDict(extra="forbid")
def load_catalog(path: Path = CATALOG_PATH) -> RulesCatalog:
    """Load the catalog from disk and validate it with Pydantic models."""

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return RulesCatalog()
    except OSError as exc:  # pragma: no cover - defensive
        raise CatalogError(f"Unable to read catalog file: {path}") from exc

    data = _safe_load_yaml(raw)
    try:
        catalog = RulesCatalog.model_validate(data)
    except ValidationError as exc:  # pragma: no cover - defensive
        raise CatalogValidationError("Catalog file is invalid") from exc
    return catalog


def parse_catalog(text: str) -> RulesCatalogDraft:
    """Parse arbitrary catalog YAML text into a draft model."""

    data = _safe_load_yaml(text)
    try:
        return RulesCatalogDraft.model_validate(data or {})
    except ValidationError as exc:
        raise CatalogValidationError("Catalog payload failed validation") from exc


def dump_catalog(catalog: RulesCatalog) -> str:
    """Serialize a catalog to YAML text."""

    payload = catalog.model_dump(mode="python")
    payload["updated_at"] = catalog.updated_at.isoformat()
    yaml_module = _ensure_yaml()
    return yaml_module.safe_dump(payload, sort_keys=False, allow_unicode=False)


def atomic_write(text: str, path: Path = CATALOG_PATH) -> None:
    """Persist ``text`` atomically to ``path``."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd: int | None = None
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(path.parent), delete=False
        ) as handle:
            tmp_fd = handle.fileno()
            tmp_path = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(tmp_fd)
        os.replace(tmp_path, path)
    except Exception:  # pragma: no cover - defensive
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def _safe_load_yaml(text: str) -> Any:
    yaml_module = _ensure_yaml()
    try:
        data = yaml_module.safe_load(text) if text.strip() else {}
    except yaml_module.YAMLError as exc:  # type: ignore[attr-defined]
        raise CatalogValidationError("Catalog YAML is not well-formed") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise CatalogValidationError("Catalog payload must be a mapping")
    return data


def rules_to_dict(rules: Iterable[Rule]) -> list[dict[str, Any]]:
    """Serialize rules to plain dictionaries for JSON responses."""

    return [rule.model_dump(mode="json") for rule in rules]


def _ensure_yaml() -> Any:
    if yaml is None:
        raise CatalogError(
            "PyYAML is required to manage rules catalog files; install the 'PyYAML' package"
        ) from _yaml_import_error
    return yaml
