from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIMPLE_SKIP = {
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    ".venv_codex",
    "env",
    ".env",
    "dist",
    "build",
    "run",
    "node_modules",
    "docs",
}


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    tests_data = PROJECT_ROOT / "tests" / "data"
    for path in PROJECT_ROOT.rglob("*.py"):
        if any(part in SIMPLE_SKIP for part in path.parts):
            continue
        if path.name == Path(__file__).name:
            continue
        try:
            if tests_data in path.parents:
                continue
        except ValueError:
            # Different drive on Windows; ignore
            pass
        files.append(path)
    return files


def test_connect_async_calls_are_awaited():
    violations: list[str] = []
    for path in _iter_python_files():
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1
        ):
            if "connectAsync" not in line:
                continue
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if "await" not in line.split("connectAsync", 1)[0]:
                violations.append(f"{path}:{lineno}")
    assert not violations, (
        "Found connectAsync invocations without an explicit await: "
        + ", ".join(violations)
    )


def test_ban_asyncio_get_event_loop():
    violations: list[str] = []
    for path in _iter_python_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "asyncio.get_event_loop(" in text or "get_event_loop_policy().get_event_loop(" in text:
            violations.append(str(path))
    assert not violations, (
        "Detected asyncio.get_event_loop usage in: " + ", ".join(violations)
    )
