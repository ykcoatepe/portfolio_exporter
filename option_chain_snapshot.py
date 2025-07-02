from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence
import zipfile

import pandas as pd

from src import data_fetching as df

choose_expiry = df.choose_expiry
pick_expiry_with_hint = df.pick_expiry_with_hint
parse_symbol_expiries = df.parse_symbol_expiries
prompt_symbol_expiries = df.prompt_symbol_expiries
fetch_yf_open_interest = df.fetch_yf_open_interest


def create_zip(files: Iterable[str], dest: str) -> None:
    """Zip given files into ``dest``."""
    with zipfile.ZipFile(dest, "w") as zf:
        for f in files:
            zf.write(f, Path(f).name)


def cleanup(files: Iterable[str]) -> None:
    for f in files:
        try:
            Path(f).unlink()
        except FileNotFoundError:
            pass
