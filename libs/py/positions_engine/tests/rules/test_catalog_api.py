# SPDX-License-Identifier: MIT

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Iterator, Tuple

import pytest
from starlette.testclient import TestClient

try:
    import yaml  # type: ignore[import]
except ModuleNotFoundError:  # pragma: no cover - environment without PyYAML
    HAS_YAML = False
else:
    HAS_YAML = True

pytestmark = pytest.mark.skipif(not HAS_YAML, reason="PyYAML required for rules catalog tests")

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from apps.api import main as api_main
from positions_engine.service.rules_catalog_state import RulesCatalogState
from positions_engine.service.rules_state import RulesState


@pytest.fixture
def catalog_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Tuple[TestClient, Path]]:
    catalog_path = tmp_path / "catalog.yaml"

    original_rules_state = api_main._rules_state
    original_catalog_state = api_main._catalog_state

    new_rules_state = RulesState(api_main._state)
    new_catalog_state = RulesCatalogState(api_main._state, new_rules_state, path=catalog_path)

    monkeypatch.setattr(api_main, "_rules_state", new_rules_state)
    monkeypatch.setattr(api_main, "_catalog_state", new_catalog_state)

    with TestClient(api_main.app) as client:
        yield client, catalog_path

    monkeypatch.setattr(api_main, "_rules_state", original_rules_state)
    monkeypatch.setattr(api_main, "_catalog_state", original_catalog_state)


def test_validate_catalog_success(catalog_client: Tuple[TestClient, Path]) -> None:
    client, _path = catalog_client
    yaml_text = """
rules:
  - rule_id: always_true
    name: Always True
    severity: INFO
    scope: PORT
    filter: ""
    expr: "True"
"""
    response = client.post("/rules/validate", json={"catalog_text": yaml_text})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["errors"] == []
    assert payload["counters"] == {"critical": 0, "warning": 0, "info": 0, "total": 0}
    assert isinstance(payload["top"], list)

    preview = client.post("/rules/preview", json={"catalog_text": yaml_text})
    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["diff"]["added"], "expected proposed catalog to add new rules"
    assert preview_payload["diff"]["removed"], "expected preview diff to include removed defaults"


def test_validate_catalog_forbidden_ast(catalog_client: Tuple[TestClient, Path]) -> None:
    client, _path = catalog_client
    yaml_text = """
rules:
  - rule_id: dangerous
    name: Dangerous Expr
    severity: INFO
    scope: PORT
    filter: ""
    expr: __import__('os').system('echo nope')
"""
    response = client.post("/rules/validate", json={"catalog_text": yaml_text})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["errors"], "expected validation errors for forbidden AST"


def test_publish_catalog_updates_summary_and_disk(catalog_client: Tuple[TestClient, Path]) -> None:
    client, catalog_path = catalog_client

    baseline_summary = client.get("/rules/summary").json()
    baseline_total = baseline_summary["rules_total"]

    yaml_text = """
rules:
  - rule_id: port_true
    name: Portfolio Always True
    severity: INFO
    scope: PORT
    filter: ""
    expr: "True"
"""
    response = client.post(
        "/rules/publish",
        json={
            "catalog_text": yaml_text,
            "author": "unit-test",
        },
    )
    assert response.status_code == 200
    publish_payload = response.json()
    assert publish_payload["version"] == 1
    assert publish_payload["updated_by"] == "unit-test"
    assert publish_payload["updated_at"].endswith("Z")

    assert catalog_path.exists()
    text_after = catalog_path.read_text(encoding="utf-8")
    assert "port_true" in text_after

    catalog_resp = client.get("/rules/catalog")
    assert catalog_resp.status_code == 200
    catalog_payload = catalog_resp.json()
    assert catalog_payload["version"] == 1
    assert len(catalog_payload["rules"]) == 1

    summary = client.get("/rules/summary").json()
    assert summary["rules_total"] == 1
    assert summary["rules_total"] != baseline_total


def test_atomic_write_prevents_partial_reads(catalog_client: Tuple[TestClient, Path]) -> None:
    client, catalog_path = catalog_client

    first_yaml = """
rules:
  - rule_id: first_rule
    name: First Rule
    severity: INFO
    scope: PORT
    filter: ""
    expr: "False"
"""
    client.post("/rules/publish", json={"catalog_text": first_yaml, "author": "initial"})
    initial_text = catalog_path.read_text(encoding="utf-8")

    second_yaml = """
rules:
  - rule_id: second_rule
    name: Second Rule
    severity: INFO
    scope: PORT
    filter: ""
    expr: "True"
  - rule_id: extra_rule
    name: Extra Rule
    severity: WARNING
    scope: PORT
    filter: ""
    expr: "True"
"""
    seen: set[str] = set()
    errors: list[str] = []
    stop_event = threading.Event()

    def reader() -> None:
        while not stop_event.is_set():
            try:
                seen.add(catalog_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                errors.append("missing")
            time.sleep(0.001)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        publish_response = client.post("/rules/publish", json={"catalog_text": second_yaml, "author": "update"})
        assert publish_response.status_code == 200
    finally:
        stop_event.set()
        thread.join(timeout=2)

    updated_text = catalog_path.read_text(encoding="utf-8")
    seen.add(updated_text)

    assert errors == []
    assert initial_text in seen
    assert updated_text in seen
    assert len(seen - {initial_text, updated_text}) == 0, "Unexpected intermediate catalog content observed"
