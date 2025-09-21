from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from time import perf_counter


class RunLog:
    """Context manager to capture run metadata and optionally write a manifest."""

    def __init__(
        self, *, script: str, args: dict | None = None, output_dir: str | Path | None = None
    ) -> None:
        self.script = script
        self.argv = args or {}
        self.output_dir = Path(output_dir) if output_dir else None
        self.start_ts = ""
        self._start = 0.0
        self.outputs: list[Path] = []
        self.timings: list[dict[str, int]] = []
        self.meta: dict = {}
        self.env = {
            "OUTPUT_DIR": os.getenv("OUTPUT_DIR"),
            "PE_OUTPUT_DIR": os.getenv("PE_OUTPUT_DIR"),
            "PE_QUIET": os.getenv("PE_QUIET"),
            "TWS_EXPORT_DIR": bool(os.getenv("TWS_EXPORT_DIR")),
            "CP_REFRESH_TOKEN": bool(os.getenv("CP_REFRESH_TOKEN")),
        }

    def __enter__(self) -> RunLog:
        self._start = perf_counter()
        self.start_ts = datetime.utcnow().isoformat()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - no special handling
        return None

    def add_outputs(self, paths: Iterable[str | Path]) -> None:
        seen = {p.resolve() for p in self.outputs}
        for p in paths:
            path = Path(p)
            if path.exists() and path.resolve() not in seen:
                self.outputs.append(path)
                seen.add(path.resolve())

    @contextmanager
    def time(self, stage: str):
        """Record elapsed milliseconds for a code block labelled *stage*."""
        start = perf_counter()
        try:
            yield
        finally:
            end = perf_counter()
            self.timings.append({"stage": stage, "ms": int((end - start) * 1000)})

    def finalize(self, *, write: bool) -> Path | None:
        end_ts = datetime.utcnow().isoformat()
        duration_ms = int((perf_counter() - self._start) * 1000)

        def _json_sanitize(obj):
            """Best-effort conversion to JSON-serializable types.

            - pathlib.Path → str
            - dict/list/tuple → recurse
            - fallback to str() for unknown objects
            """
            if isinstance(obj, Path):
                return str(obj)
            if isinstance(obj, dict):
                return {k: _json_sanitize(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_json_sanitize(v) for v in (list(obj) if isinstance(obj, tuple) else obj)]
            try:
                json.dumps(obj)
                return obj
            except Exception:
                return str(obj)

        outs: list[dict[str, object]] = []
        for p in self.outputs:
            try:
                data = p.read_bytes()
            except Exception:
                continue
            sha = hashlib.sha256(data).hexdigest()
            outs.append({"path": str(p), "sha256": sha, "bytes": len(data)})
        manifest = {
            "script": self.script,
            "argv": _json_sanitize(self.argv),
            "env": self.env,
            "start": self.start_ts,
            "end": end_ts,
            "duration_ms": duration_ms,
            "outputs": outs,
            "warnings": [],
            "version": None,
            "meta": _json_sanitize(self.meta) if self.meta else {},
        }
        if write and self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            mpath = self.output_dir / f"{self.script}_manifest.json"
            with mpath.open("w") as fh:
                json.dump(manifest, fh, indent=2)
            return mpath
        return None

    def add_meta(self, data: dict) -> None:
        """Merge additional metadata to be written in the manifest."""
        try:
            self.meta.update(data or {})
        except Exception:
            pass
