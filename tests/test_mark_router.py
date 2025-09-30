# SPDX-License-Identifier: MIT
from __future__ import annotations

import time

from psd.core.mark_router import Session, choose_mark

_EXT: Session = "EXT"


def _tick(ts_offset: float = 0.0, **fields: float) -> dict[str, float]:
    tick = {"ts": time.time() - ts_offset}
    tick.update(fields)
    return tick


def test_choose_mark_ext_prefers_mid_over_last() -> None:
    mark, source, _ = choose_mark(_tick(mid=1.25, last=1.4), _EXT)
    assert mark == 1.25
    assert source == "mid"


def test_choose_mark_ext_uses_last_when_mid_missing() -> None:
    mark, source, _ = choose_mark(_tick(last=2.5), _EXT)
    assert mark == 2.5
    assert source == "last"


def test_choose_mark_ext_falls_back_to_last_close() -> None:
    mark, source, _ = choose_mark(_tick(last_close=3.1), _EXT)
    assert source == "last_close"
    assert mark == 3.1
