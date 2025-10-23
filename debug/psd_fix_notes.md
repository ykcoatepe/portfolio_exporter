ruff check . && pytest -q || true
apps/api/main.py:273:44: UP017 [*] Use `datetime.UTC` alias
    |
271 |     _state.refresh_live_snapshot()
272 |     _state.refresh_live_greeks()
273 |     return {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}
    |                                            ^^^^^^^^^^^^ UP017
    |
    = help: Convert to `datetime.UTC` alias

apps/cli/run.py:9:1: UP035 [*] Import from `collections.abc` instead: `Iterable`, `Mapping`
   |
 7 | from dataclasses import asdict
 8 | from pathlib import Path
 9 | from typing import Any, Iterable, Mapping
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ UP035
10 |
11 | MODULE_PATH = Path(__file__).resolve()
   |
   = help: Import from `collections.abc`

apps/cli/run.py:9:35: F401 [*] `typing.Mapping` imported but unused
   |
 7 | from dataclasses import asdict
 8 | from pathlib import Path
 9 | from typing import Any, Iterable, Mapping
   |                                   ^^^^^^^ F401
10 |
11 | MODULE_PATH = Path(__file__).resolve()
   |
   = help: Remove unused import: `typing.Mapping`

libs/py/positions_engine/combos/grouping.py:5:1: I001 [*] Import block is un-sorted or un-formatted
   |
 3 |   """Helpers for grouping duplicate option combos and generating labels."""
 4 |
 5 | / from __future__ import annotations
 6 | |
 7 | | from collections import defaultdict
 8 | | from collections.abc import Sequence
 9 | | from dataclasses import dataclass, field
10 | | from datetime import date
11 | | from decimal import Decimal, InvalidOperation
12 | | from typing import Any
13 | | import math
14 | |
15 | | from .detector import OptionCombo, OptionLegSnapshot
16 | | from .taxonomy import ComboStrategy
   | |___________________________________^ I001
17 |
18 |   ZERO = Decimal("0")
   |
   = help: Organize imports

libs/py/positions_engine/service/refresh.py:9:1: UP035 [*] Import from `collections.abc` instead: `Callable`
  |
7 | import os
8 | import threading
9 | from typing import Callable, Optional
  | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ UP035
  |
  = help: Import from `collections.abc`

libs/py/positions_engine/service/refresh.py:18:21: UP045 [*] Use `X | None` for type annotations
   |
16 |         self,
17 |         tick: Callable[[], None],
18 |         interval_s: Optional[float] = None,
   |                     ^^^^^^^^^^^^^^^ UP045
19 |         *,
20 |         env_var: str = "PSD_REFRESH_INTERVAL_S",
   |
   = help: Convert to `X | None`

libs/py/positions_engine/service/refresh.py:25:23: UP045 [*] Use `X | None` for type annotations
   |
23 |         self._interval = _resolve_interval(env_var, interval_s)
24 |         self._stop = threading.Event()
25 |         self._thread: Optional[threading.Thread] = None
   |                       ^^^^^^^^^^^^^^^^^^^^^^^^^^ UP045
26 |
27 |     def start(self) -> None:
   |
   = help: Convert to `X | None`

libs/py/positions_engine/service/refresh.py:52:47: UP045 [*] Use `X | None` for type annotations
   |
52 | def _resolve_interval(env_var: str, fallback: Optional[float]) -> float:
   |                                               ^^^^^^^^^^^^^^^ UP045
53 |     env_value = os.getenv(env_var)
54 |     if env_value is not None:
   |
   = help: Convert to `X | None`

libs/py/positions_engine/tests/combos/test_grouping.py:1:1: I001 [*] Import block is un-sorted or un-formatted
   |
 1 | / from __future__ import annotations
 2 | |
 3 | | from datetime import UTC, datetime
 4 | | from decimal import Decimal
 5 | |
 6 | | import pytest
 7 | |
 8 | | from positions_engine.combos import (
 9 | |     ComboStrategy,
10 | |     OptionCombo,
11 | |     OptionLegSnapshot,
12 | |     group_option_combos,
13 | | )
14 | | from positions_engine.core.models import (
15 | |     Instrument,
16 | |     InstrumentType,
17 | |     Position,
18 | |     Quote,
19 | |     TradingSession,
20 | | )
21 | | from positions_engine.service.state import PositionsState
   | |_________________________________________________________^ I001
22 |
23 |   NOW = datetime(2025, 2, 15, 15, 30, tzinfo=UTC)
   |
   = help: Organize imports

libs/py/positions_engine/tests/rules/test_api_rules.py:17:1: I001 [*] Import block is un-sorted or un-formatted
   |
15 |       sys.path.append(str(ROOT))
16 |
17 | / from positions_engine.combos.detector import ComboDetection, OptionCombo, OptionLegSnapshot
18 | | from positions_engine.combos.taxonomy import ComboStrategy
19 | | from positions_engine.rules import Rule
20 | | from positions_engine.service.rules_state import RulesState
21 | |
22 | | from apps.api import main as api_main
   | |_____________________________________^ I001
   |
   = help: Organize imports

Found 10 errors.
[*] 10 fixable with the `--fix` option.
ruff check . && pytest -q || true
apps/api/main.py:12:37: F401 [*] `datetime.timezone` imported but unused
   |
10 | import sys
11 | from dataclasses import asdict
12 | from datetime import UTC, datetime, timezone
   |                                     ^^^^^^^^ F401
13 | from pathlib import Path
14 | from typing import Any, Literal
   |
   = help: Remove unused import: `datetime.timezone`

libs/py/positions_engine/tests/test_psd_regressions.py:5:1: I001 [*] Import block is un-sorted or un-formatted
   |
 3 |   """Regression tests for PSD cost basis, staleness, and leg mark handling."""
 4 |
 5 | / from __future__ import annotations
 6 | |
 7 | | from datetime import UTC, datetime, timedelta
 8 | | from decimal import Decimal
 9 | |
10 | | import pytest
11 | |
12 | | from positions_engine.core.models import Instrument, InstrumentType, Position, Quote, TradingSession
13 | | from positions_engine.ingest.internal import InternalScriptsProvider
14 | | from positions_engine.service.normalize import compute_equity_pnl_fields
15 | | from positions_engine.service.state import (
16 | |     PositionsState,
17 | |     _normalize_option_mark_payload,
18 | |     _resolve_option_stale_seconds_entry,
19 | | )
   | |_^ I001
   |
   = help: Organize imports

Found 2 errors.
[*] 2 fixable with the `--fix` option.
ruff check . && pytest -q || true
All checks passed!

==================================== ERRORS ====================================
___ ERROR collecting libs/py/positions_engine/tests/combos/test_detector.py ____
libs/py/positions_engine/tests/combos/test_detector.py:6: in <module>
    from positions_engine.combos import (
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
___ ERROR collecting libs/py/positions_engine/tests/combos/test_group_qty.py ___
libs/py/positions_engine/tests/combos/test_group_qty.py:5: in <module>
    from positions_engine.combos import (
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
___ ERROR collecting libs/py/positions_engine/tests/combos/test_grouping.py ____
libs/py/positions_engine/tests/combos/test_grouping.py:7: in <module>
    from positions_engine.combos import (
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
__ ERROR collecting libs/py/positions_engine/tests/combos/test_mark_source.py __
libs/py/positions_engine/tests/combos/test_mark_source.py:10: in <module>
    from positions_engine.combos import (
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
____ ERROR collecting libs/py/positions_engine/tests/options/test_tp_sl.py _____
libs/py/positions_engine/tests/options/test_tp_sl.py:7: in <module>
    from positions_engine.combos.detector import (
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
___ ERROR collecting libs/py/positions_engine/tests/rules/test_api_rules.py ____
libs/py/positions_engine/tests/rules/test_api_rules.py:17: in <module>
    from positions_engine.combos.detector import (
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
__ ERROR collecting libs/py/positions_engine/tests/rules/test_catalog_api.py ___
libs/py/positions_engine/tests/rules/test_catalog_api.py:20: in <module>
    from positions_engine.service.rules_catalog_state import RulesCatalogState
libs/py/positions_engine/service/__init__.py:7: in <module>
    from .rules_catalog_state import RulesCatalogState
libs/py/positions_engine/service/rules_catalog_state.py:26: in <module>
    from .rules_state import RulesState
libs/py/positions_engine/service/rules_state.py:14: in <module>
    from ..combos.detector import OptionCombo, OptionLegSnapshot
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
________ ERROR collecting libs/py/positions_engine/tests/test_marks.py _________
libs/py/positions_engine/tests/test_marks.py:10: in <module>
    from positions_engine.service.state import PositionsState
libs/py/positions_engine/service/__init__.py:7: in <module>
    from .rules_catalog_state import RulesCatalogState
libs/py/positions_engine/service/rules_catalog_state.py:26: in <module>
    from .rules_state import RulesState
libs/py/positions_engine/service/rules_state.py:14: in <module>
    from ..combos.detector import OptionCombo, OptionLegSnapshot
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
__ ERROR collecting libs/py/positions_engine/tests/test_option_timestamps.py ___
libs/py/positions_engine/tests/test_option_timestamps.py:7: in <module>
    from positions_engine.service.state import _normalize_option_leg_entry
libs/py/positions_engine/service/__init__.py:7: in <module>
    from .rules_catalog_state import RulesCatalogState
libs/py/positions_engine/service/rules_catalog_state.py:26: in <module>
    from .rules_state import RulesState
libs/py/positions_engine/service/rules_state.py:14: in <module>
    from ..combos.detector import OptionCombo, OptionLegSnapshot
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
_ ERROR collecting libs/py/positions_engine/tests/test_options_endpoint_marks.py _
libs/py/positions_engine/tests/test_options_endpoint_marks.py:15: in <module>
    from positions_engine.service.state import PositionsState
libs/py/positions_engine/service/__init__.py:7: in <module>
    from .rules_catalog_state import RulesCatalogState
libs/py/positions_engine/service/rules_catalog_state.py:26: in <module>
    from .rules_state import RulesState
libs/py/positions_engine/service/rules_state.py:14: in <module>
    from ..combos.detector import OptionCombo, OptionLegSnapshot
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
___ ERROR collecting libs/py/positions_engine/tests/test_psd_regressions.py ____
libs/py/positions_engine/tests/test_psd_regressions.py:20: in <module>
    from positions_engine.service.state import (
libs/py/positions_engine/service/__init__.py:7: in <module>
    from .rules_catalog_state import RulesCatalogState
libs/py/positions_engine/service/rules_catalog_state.py:26: in <module>
    from .rules_state import RulesState
libs/py/positions_engine/service/rules_state.py:14: in <module>
    from ..combos.detector import OptionCombo, OptionLegSnapshot
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
________ ERROR collecting libs/py/positions_engine/tests/test_state.py _________
libs/py/positions_engine/tests/test_state.py:15: in <module>
    from positions_engine.service.state import PositionsState
libs/py/positions_engine/service/__init__.py:7: in <module>
    from .rules_catalog_state import RulesCatalogState
libs/py/positions_engine/service/rules_catalog_state.py:26: in <module>
    from .rules_state import RulesState
libs/py/positions_engine/service/rules_state.py:14: in <module>
    from ..combos.detector import OptionCombo, OptionLegSnapshot
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
__________ ERROR collecting tests/options/test_osi_normalize_group.py __________
tests/options/test_osi_normalize_group.py:9: in <module>
    from positions_engine.combos import (
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
________________ ERROR collecting tests/test_ingest_internal.py ________________
tests/test_ingest_internal.py:6: in <module>
    import apps.api.main as api
apps/api/main.py:39: in <module>
    from positions_engine.service import (  # noqa: E402
libs/py/positions_engine/service/__init__.py:7: in <module>
    from .rules_catalog_state import RulesCatalogState
libs/py/positions_engine/service/rules_catalog_state.py:26: in <module>
    from .rules_state import RulesState
libs/py/positions_engine/service/rules_state.py:14: in <module>
    from ..combos.detector import OptionCombo, OptionLegSnapshot
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
______ ERROR collecting tests/test_positions_engine_combo_exit_as_unit.py ______
tests/test_positions_engine_combo_exit_as_unit.py:5: in <module>
    from positions_engine.combos.detector import OptionCombo, OptionLegSnapshot
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
________ ERROR collecting tests/test_positions_engine_timestamp_zero.py ________
tests/test_positions_engine_timestamp_zero.py:3: in <module>
    from positions_engine.service.state import (
libs/py/positions_engine/service/__init__.py:7: in <module>
    from .rules_catalog_state import RulesCatalogState
libs/py/positions_engine/service/rules_catalog_state.py:26: in <module>
    from .rules_state import RulesState
libs/py/positions_engine/service/rules_state.py:14: in <module>
    from ..combos.detector import OptionCombo, OptionLegSnapshot
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
___________ ERROR collecting tests/test_positions_state_snapshot.py ____________
tests/test_positions_state_snapshot.py:8: in <module>
    from positions_engine.service.state import PositionsState
libs/py/positions_engine/service/__init__.py:7: in <module>
    from .rules_catalog_state import RulesCatalogState
libs/py/positions_engine/service/rules_catalog_state.py:26: in <module>
    from .rules_state import RulesState
libs/py/positions_engine/service/rules_state.py:14: in <module>
    from ..combos.detector import OptionCombo, OptionLegSnapshot
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
_________________ ERROR collecting tests/test_refresh_loop.py __________________
tests/test_refresh_loop.py:15: in <module>
    from positions_engine.service import PositionsState, RefreshLoop
libs/py/positions_engine/service/__init__.py:7: in <module>
    from .rules_catalog_state import RulesCatalogState
libs/py/positions_engine/service/rules_catalog_state.py:26: in <module>
    from .rules_state import RulesState
libs/py/positions_engine/service/rules_state.py:14: in <module>
    from ..combos.detector import OptionCombo, OptionLegSnapshot
libs/py/positions_engine/combos/__init__.py:5: in <module>
    from .detector import (
libs/py/positions_engine/combos/detector.py:24: in <module>
    @dataclass(frozen=True)
     ^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1295: in wrap
    return _process_class(cls, init, repr, eq, order, unsafe_hash,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:1078: in _process_class
    _init_fn(all_init_fields,
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/dataclasses.py:627: in _init_fn
    raise TypeError(f'non-default argument {f.name!r} '
E   TypeError: non-default argument 'mark' follows default argument 'avg_cost'
=============================== warnings summary ===============================
.venv/lib/python3.13/site-packages/_pytest/config/__init__.py:1474
  /Users/yordamkocatepe/PycharmProjects/portfolio_exporter/.venv/lib/python3.13/site-packages/_pytest/config/__init__.py:1474: PytestConfigWarning: Unknown config option: timeout
  
    self._warn_or_fail_if_strict(f"Unknown config option: {key}\n")

.venv/lib/python3.13/site-packages/_pytest/config/__init__.py:1474
  /Users/yordamkocatepe/PycharmProjects/portfolio_exporter/.venv/lib/python3.13/site-packages/_pytest/config/__init__.py:1474: PytestConfigWarning: Unknown config option: timeout_method
  
    self._warn_or_fail_if_strict(f"Unknown config option: {key}\n")

.venv/lib/python3.13/site-packages/eventkit/util.py:21
  /Users/yordamkocatepe/PycharmProjects/portfolio_exporter/.venv/lib/python3.13/site-packages/eventkit/util.py:21: DeprecationWarning: There is no current event loop
    return asyncio.get_event_loop_policy().get_event_loop()

.venv/lib/python3.13/site-packages/pandera/_pandas_deprecated.py:160
  /Users/yordamkocatepe/PycharmProjects/portfolio_exporter/.venv/lib/python3.13/site-packages/pandera/_pandas_deprecated.py:160: FutureWarning: Importing pandas-specific classes and functions from the
  top-level pandera module will be **removed in a future version of pandera**.
  If you're using pandera to validate pandas objects, we highly recommend updating
  your import:
  
  ```
  # old import
  import pandera as pa
  
  # new import
  import pandera.pandas as pa
  ```
  
  If you're using pandera to validate objects from other compatible libraries
  like pyspark or polars, see the supported libraries section of the documentation
  for more information on how to import pandera:
  
  https://pandera.readthedocs.io/en/stable/supported_libraries.html
  
  To disable this warning, set the environment variable:
  
  ```
  export DISABLE_PANDERA_IMPORT_WARNING=True
  ```
  
    warnings.warn(_future_warning, FutureWarning)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
ERROR libs/py/positions_engine/tests/combos/test_detector.py - TypeError: non...
ERROR libs/py/positions_engine/tests/combos/test_group_qty.py - TypeError: no...
ERROR libs/py/positions_engine/tests/combos/test_grouping.py - TypeError: non...
ERROR libs/py/positions_engine/tests/combos/test_mark_source.py - TypeError: ...
ERROR libs/py/positions_engine/tests/options/test_tp_sl.py - TypeError: non-d...
ERROR libs/py/positions_engine/tests/rules/test_api_rules.py - TypeError: non...
ERROR libs/py/positions_engine/tests/rules/test_catalog_api.py - TypeError: n...
ERROR libs/py/positions_engine/tests/test_marks.py - TypeError: non-default a...
ERROR libs/py/positions_engine/tests/test_option_timestamps.py - TypeError: n...
ERROR libs/py/positions_engine/tests/test_options_endpoint_marks.py - TypeErr...
ERROR libs/py/positions_engine/tests/test_psd_regressions.py - TypeError: non...
ERROR libs/py/positions_engine/tests/test_state.py - TypeError: non-default a...
ERROR tests/options/test_osi_normalize_group.py - TypeError: non-default argu...
ERROR tests/test_ingest_internal.py - TypeError: non-default argument 'mark' ...
ERROR tests/test_positions_engine_combo_exit_as_unit.py - TypeError: non-defa...
ERROR tests/test_positions_engine_timestamp_zero.py - TypeError: non-default ...
ERROR tests/test_positions_state_snapshot.py - TypeError: non-default argumen...
ERROR tests/test_refresh_loop.py - TypeError: non-default argument 'mark' fol...
!!!!!!!!!!!!!!!!!!! Interrupted: 18 errors during collection !!!!!!!!!!!!!!!!!!!
ruff check . && pytest -q || true
All checks passed!

==================================== ERRORS ====================================
________ ERROR collecting tests/test_positions_engine_timestamp_zero.py ________
ImportError while importing test module '/Users/yordamkocatepe/PycharmProjects/portfolio_exporter/tests/test_positions_engine_timestamp_zero.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_positions_engine_timestamp_zero.py:3: in <module>
    from positions_engine.service.state import (
E   ImportError: cannot import name '_PREV_STALE_FALLBACK_SECONDS' from 'positions_engine.service.state' (/Users/yordamkocatepe/PycharmProjects/portfolio_exporter/libs/py/positions_engine/service/state.py)
=============================== warnings summary ===============================
.venv/lib/python3.13/site-packages/_pytest/config/__init__.py:1474
  /Users/yordamkocatepe/PycharmProjects/portfolio_exporter/.venv/lib/python3.13/site-packages/_pytest/config/__init__.py:1474: PytestConfigWarning: Unknown config option: timeout
  
    self._warn_or_fail_if_strict(f"Unknown config option: {key}\n")

.venv/lib/python3.13/site-packages/_pytest/config/__init__.py:1474
  /Users/yordamkocatepe/PycharmProjects/portfolio_exporter/.venv/lib/python3.13/site-packages/_pytest/config/__init__.py:1474: PytestConfigWarning: Unknown config option: timeout_method
  
    self._warn_or_fail_if_strict(f"Unknown config option: {key}\n")

.venv/lib/python3.13/site-packages/pydantic/_internal/_config.py:323
  /Users/yordamkocatepe/PycharmProjects/portfolio_exporter/.venv/lib/python3.13/site-packages/pydantic/_internal/_config.py:323: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.11/migration/
    warnings.warn(DEPRECATION_MESSAGE, DeprecationWarning)

apps/api/main.py:249
  /Users/yordamkocatepe/PycharmProjects/portfolio_exporter/apps/api/main.py:249: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    @app.on_event("startup")

.venv/lib/python3.13/site-packages/fastapi/applications.py:4523
.venv/lib/python3.13/site-packages/fastapi/applications.py:4523
  /Users/yordamkocatepe/PycharmProjects/portfolio_exporter/.venv/lib/python3.13/site-packages/fastapi/applications.py:4523: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    return self.router.on_event(event_type)

apps/api/main.py:257
  /Users/yordamkocatepe/PycharmProjects/portfolio_exporter/apps/api/main.py:257: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    @app.on_event("shutdown")

.venv/lib/python3.13/site-packages/eventkit/util.py:21
  /Users/yordamkocatepe/PycharmProjects/portfolio_exporter/.venv/lib/python3.13/site-packages/eventkit/util.py:21: DeprecationWarning: There is no current event loop
    return asyncio.get_event_loop_policy().get_event_loop()

.venv/lib/python3.13/site-packages/pandera/_pandas_deprecated.py:160
  /Users/yordamkocatepe/PycharmProjects/portfolio_exporter/.venv/lib/python3.13/site-packages/pandera/_pandas_deprecated.py:160: FutureWarning: Importing pandas-specific classes and functions from the
  top-level pandera module will be **removed in a future version of pandera**.
  If you're using pandera to validate pandas objects, we highly recommend updating
  your import:
  
  ```
  # old import
  import pandera as pa
  
  # new import
  import pandera.pandas as pa
  ```
  
  If you're using pandera to validate objects from other compatible libraries
  like pyspark or polars, see the supported libraries section of the documentation
  for more information on how to import pandera:
  
  https://pandera.readthedocs.io/en/stable/supported_libraries.html
  
  To disable this warning, set the environment variable:
  
  ```
  export DISABLE_PANDERA_IMPORT_WARNING=True
  ```
  
    warnings.warn(_future_warning, FutureWarning)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
ERROR tests/test_positions_engine_timestamp_zero.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
ruff check . && pytest -q || true
All checks passed!
..................................make: *** [sanity-fast] Terminated: 15

## Fri Sep 26 09:00:32 UTC 2025 make sanity-fast
ruff check . && pytest -q || true
All checks passed!
..................................ruff check . && pytest -q || true
All checks passed!
..................................