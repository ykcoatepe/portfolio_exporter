from __future__ import annotations

import time
from pathlib import Path

from portfolio_exporter.core.fs_utils import auto_chains_dir, auto_config, find_latest_file


def test_find_latest_file(tmp_path: Path) -> None:
    d = tmp_path
    f1 = d / "meme_scan_20240101.csv"
    f2 = d / "meme_scan_20240315.csv"
    f1.write_text("a\n")
    time.sleep(0.01)
    f2.write_text("b\n")
    time.sleep(0.01)
    f1.touch()
    p = find_latest_file([str(d)], ["meme_scan_*.csv"])
    assert p and p.endswith("meme_scan_20240315.csv")


def test_auto_config(tmp_path: Path) -> None:
    cfg = tmp_path / "micro_momo_config.json"
    cfg.write_text("{}")
    out = auto_config([str(cfg), None])
    assert out and out.endswith("micro_momo_config.json")


def test_auto_chains_dir(tmp_path: Path) -> None:
    chains = tmp_path / "chains"
    chains.mkdir()
    out = auto_chains_dir([str(chains), None])
    assert out and out.endswith("chains")

