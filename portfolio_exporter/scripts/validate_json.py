"""Validate JSON summaries against local schemas."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema


SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


def validate(obj: dict) -> None:
    schema_id = obj.get("meta", {}).get("schema_id")
    if not schema_id:
        raise SystemExit("missing meta.schema_id")
    path = SCHEMA_DIR / f"{schema_id}.schema.json"
    with path.open() as fh:
        schema = json.load(fh)
    jsonschema.validate(obj, schema)


def main(argv: list[str] | None = None) -> int:
    data = json.load(sys.stdin)
    validate(data)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
