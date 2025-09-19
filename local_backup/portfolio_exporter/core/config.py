from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    timezone: str = os.environ.get("PE_TIMEZONE", "Europe/Istanbul")
    output_dir: Path = Path(os.environ.get("OUTPUT_DIR", ".")).resolve()


settings = Settings()
