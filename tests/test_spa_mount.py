from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not Path("apps/web/dist/index.html").exists(),
    reason="PSD bundle has not been built (apps/web/dist/index.html missing)",
)


def test_spa_mount_serves_psd_and_preserves_api():
    from apps.api.main import INDEX_HTML, app

    assert INDEX_HTML.exists(), "Expected PSD index.html to exist for SPA serving"

    client = TestClient(app)

    resp = client.get("/psd")
    assert resp.status_code == 200
    content_type = resp.headers.get("content-type", "")
    assert "text/html" in content_type.lower()

    api_resp = client.get("/positions/stocks")
    assert api_resp.status_code == 200
    api_content_type = api_resp.headers.get("content-type", "")
    assert api_content_type.startswith("application/json"), api_content_type

    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200

    openapi_resp = client.get("/openapi.json")
    assert openapi_resp.status_code == 200
    openapi_content_type = openapi_resp.headers.get("content-type", "")
    assert openapi_content_type.startswith("application/json"), openapi_content_type
