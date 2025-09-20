#!/usr/bin/env python3
import json
import pathlib


def ensure_memory_file(path: pathlib.Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"worklog": []}
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    tmp_path.replace(path)


def main() -> None:
    memory_path = pathlib.Path(".codex/memory.json")
    ensure_memory_file(memory_path)
    print(f"memory: OK -> {memory_path}")


if __name__ == "__main__":
    main()
