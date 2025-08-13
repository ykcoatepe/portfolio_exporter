from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Iterable, List


class RunLog:
    """Context manager to capture run metadata and optionally write a manifest."""

    def __init__(self, *, script: str, args: dict | None = None, output_dir: str | Path | None = None) -> None:
        self.script = script
        self.argv = args or {}
        self.output_dir = Path(output_dir) if output_dir else None
        self.start_ts = ""
        self._start = 0.0
        self.outputs: List[Path] = []
        self.env = {
            "OUTPUT_DIR": os.getenv("OUTPUT_DIR"),
            "PE_OUTPUT_DIR": os.getenv("PE_OUTPUT_DIR"),
            "PE_QUIET": os.getenv("PE_QUIET"),
            "TWS_EXPORT_DIR": bool(os.getenv("TWS_EXPORT_DIR")),
            "CP_REFRESH_TOKEN": bool(os.getenv("CP_REFRESH_TOKEN")),
        }

    def __enter__(self) -> "RunLog":
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

    def finalize(self, *, write: bool) -> Path | None:
        end_ts = datetime.utcnow().isoformat()
        duration_ms = int((perf_counter() - self._start) * 1000)
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
            "argv": self.argv,
            "env": self.env,
            "start": self.start_ts,
            "end": end_ts,
            "duration_ms": duration_ms,
            "outputs": outs,
            "warnings": [],
            "version": None,
        }
        if write and self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            mpath = self.output_dir / f"{self.script}_manifest.json"
            with mpath.open("w") as fh:
                json.dump(manifest, fh, indent=2)
            return mpath
        return None
