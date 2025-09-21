import pytest

try:
    from starlette.testclient import TestClient
except (RuntimeError, ModuleNotFoundError) as exc:  # pragma: no cover - env guard
    pytest.skip(str(exc), allow_module_level=True)

from psd.web.app import app


def test_metrics_smoke() -> None:
    # Using context manager ensures FastAPI lifespan hooks run.
    with TestClient(app) as client:
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
        body = response.text
        assert "psd_events_total" in body
