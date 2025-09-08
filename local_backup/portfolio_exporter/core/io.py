from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import pandas as pd


def save(obj: Any, base_name: str, fmt: str, outdir: Path | str) -> Path:
    """Save a DataFrame or JSON-serializable object to outdir.

    Returns the path written.
    """
    outdir_path = Path(outdir)
    outdir_path.mkdir(parents=True, exist_ok=True)

    if fmt.lower() == "csv":
        if isinstance(obj, pd.DataFrame):
            path = outdir_path / f"{base_name}.csv"
            obj.to_csv(path, index=False)
            return path
        # Fallback: try to coerce list/dict to DataFrame
        path = outdir_path / f"{base_name}.csv"
        try:
            pd.DataFrame(obj).to_csv(path, index=False)  # type: ignore[arg-type]
            return path
        except Exception:
            # write JSON instead if coercion fails
            path = outdir_path / f"{base_name}.json"
            with path.open("w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False)
            return path

    # Default to JSON
    path = outdir_path / f"{base_name}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, default=_json_default)
    return path


def latest_file(prefix: str, outdir: Path | str) -> Path | None:
    """Return the latest file in outdir that starts with prefix."""
    p = Path(outdir)
    if not p.exists():
        return None
    cand = sorted(p.glob(f"{prefix}*"), key=lambda x: x.stat().st_mtime)
    return cand[-1] if cand else None


def _json_default(o: object) -> Any:
    try:
        import pandas as pd  # local import for type

        if isinstance(o, pd.Timestamp):
            return o.isoformat()
    except Exception:
        pass
    return str(o)

