# Repository Guidelines for Codex Agents

## Testing
- Always run `pytest` from the repository root after making changes.
- Install dev dependencies with `pip install -r requirements-dev.txt` if tests fail due to missing packages.

## Style
- Format Python code with **black** using the default configuration (line length 88).
- Keep imports organized and remove unused imports.
- Use descriptive variable names and add type hints for new functions where practical.

## General
- Keep commit messages concise, e.g. "Add option chain helper".
- Avoid network calls in tests; rely on stubs or fixtures.
- Python version is 3.11+.
