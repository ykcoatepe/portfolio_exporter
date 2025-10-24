from __future__ import annotations

from pathlib import Path

from psd.datasources import is_offline
from psd.datasources.fred import refresh_hy_csv


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


def test_refresh_hy_csv_offline(tmp_path: Path) -> None:
    target = tmp_path / "hy.csv"
    env = {"PE_TEST_MODE": "1", "FRED_API_KEY": "dummy"}
    assert is_offline(env)
    assert refresh_hy_csv(target, env=env) is False
    assert not target.exists()


def test_refresh_hy_csv_writes_rows(tmp_path: Path) -> None:
    target = tmp_path / "hy.csv"

    class _Session:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, *_args, **_kwargs):
            self.calls += 1
            payload = {
                "observations": [
                    {"date": "2024-09-30", "value": "4.12"},
                    {"date": "2024-10-01", "value": "4.18"},
                ]
            }
            return _DummyResponse(200, payload)

        def close(self) -> None:  # pragma: no cover - ensure compatibility
            pass

    session = _Session()
    updated = refresh_hy_csv(
        target,
        env={"FRED_API_KEY": "dummy"},
        session=session,
    )
    assert updated is True
    assert session.calls == 1
    contents = target.read_text().splitlines()
    assert contents[0] == "date,value"
    assert "2024-10-01,4.18" in contents[-1]


def test_refresh_hy_csv_retries_on_rate_limit(tmp_path: Path) -> None:
    target = tmp_path / "hy.csv"

    class _Session:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return _DummyResponse(429, {"error_code": 429})
            return _DummyResponse(
                200,
                {
                    "observations": [
                        {"date": "2024-10-02", "value": "4.21"},
                    ]
                },
            )

        def close(self) -> None:  # pragma: no cover
            pass

    session = _Session()
    updated = refresh_hy_csv(
        target,
        env={"FRED_API_KEY": "dummy"},
        session=session,
        max_retries=3,
        backoff_seconds=0.01,
    )
    assert updated is True
    assert session.calls == 2
