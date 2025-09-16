"""
Task planner and runner for portfolio_exporter scripts.

Features:
- Discover runnable tasks from `portfolio_exporter.scripts` modules that expose `main(...)`.
- Print a registry via `--list-tasks`.
- Build an execution plan without running via `--dry-run`.
- Expand workflows from `.codex/memory.json` using key `workflows.submenu_queue[<name>]`.

Note: Designed to be lightweight and avoid importing heavy script modules at startup.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional


SCRIPTS_PACKAGE_DIR = Path(__file__).parent / "scripts"
DEFAULT_MEMORY_PATH = Path(".codex/memory.json")


@dataclass(frozen=True)
class Task:
    name: str
    module: str  # fully qualified module path under portfolio_exporter.scripts


def _iter_script_modules() -> Iterable[Path]:
    if not SCRIPTS_PACKAGE_DIR.exists():
        return []
    for p in sorted(SCRIPTS_PACKAGE_DIR.glob("*.py")):
        if p.name.startswith("_"):
            continue
        yield p


def _has_main_function(py_file: Path) -> bool:
    # Fast, import-free check: scan for a top-level "def main("
    try:
        with py_file.open("r", encoding="utf-8", errors="ignore") as f:
            head = f.read()
        return "def main(" in head
    except OSError:
        return False


def discover_tasks() -> list[Task]:
    tasks: list[Task] = []
    for f in _iter_script_modules():
        if not _has_main_function(f):
            continue
        name = f.stem
        module = f"portfolio_exporter.scripts.{name}"
        tasks.append(Task(name=name, module=module))
    return tasks


def read_workflow(memory_path: Path, workflow_name: str) -> list[str]:
    if not memory_path.exists():
        return []
    try:
        with memory_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    # Expected shape: { "workflows": { "submenu_queue": { "<name>": ["task", ...] } } }
    wf = (
        data.get("workflows", {})
        .get("submenu_queue", {})
        .get(workflow_name, [])
    )
    if isinstance(wf, list):
        return [str(x) for x in wf]
    return []


def build_parser() -> argparse.ArgumentParser:
    epilog = (
        "Pro tips: Multi-select supported (e.g., 2,4 or 1-3) — use hotkeys to quickly "
        "toggle selections and run a dry-run before executing."
    )
    p = argparse.ArgumentParser(
        description="Task discovery and planner for portfolio_exporter scripts",
        epilog=epilog,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument(
        "--task",
        help="Run a single custom task by name (e.g., micro-momo)",
    )
    p.add_argument(
        "--list-tasks",
        action="store_true",
        help="List discovered runnable tasks and exit",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show execution plan without running tasks",
    )
    p.add_argument(
        "--workflow",
        metavar="NAME",
        help="Expand tasks from .codex/memory.json workflows.submenu_queue[NAME]",
    )
    p.add_argument(
        "--select",
        metavar="IDX[,IDX|-RANGE]",
        help=(
            "Select tasks by number from the discovery list (e.g., '2,4-6'). "
            "Indices are 1-based and can be combined with names/workflow."
        ),
    )
    p.add_argument(
        "tasks",
        nargs="*",
        help="Task names to queue (overrides workflow if provided)",
    )
    p.add_argument(
        "--memory-path",
        type=Path,
        default=DEFAULT_MEMORY_PATH,
        help="Path to memory.json (default: .codex/memory.json)",
    )
    p.add_argument(
        "--bootstrap-memory",
        action="store_true",
        help=(
            "Run 'python -m portfolio_exporter.scripts.memory bootstrap' before processing. "
            "Honors MEMORY_READONLY."
        ),
    )
    return p


def _print_registry(tasks: list[Task]) -> None:
    if not tasks:
        print("No tasks discovered under portfolio_exporter.scripts")
        return
    print("Discovered tasks:")
    for i, t in enumerate(tasks, start=1):
        print(f"  {i:>2}. {t.name}  ({t.module})")


def _resolve_queue(
    registry: list[Task], requested: list[str]
) -> list[Task]:
    reg_by_name = {t.name: t for t in registry}
    queue: list[Task] = []
    for name in requested:
        t = reg_by_name.get(name)
        if t:
            queue.append(t)
    return queue


def _parse_selection_expr(expr: str, upper: int) -> list[int]:
    # Parse comma-separated tokens which may be single 1-based indices or ranges like 2-5
    indices: list[int] = []
    if not expr:
        return indices
    for token in expr.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            try:
                start = int(a)
                end = int(b)
            except ValueError:
                continue
            if start <= 0 or end <= 0:
                continue
            if start > end:
                start, end = end, start
            for i in range(start, end + 1):
                if 1 <= i <= upper:
                    indices.append(i)
        else:
            try:
                i = int(token)
            except ValueError:
                continue
            if 1 <= i <= upper:
                indices.append(i)
    # Preserve order but drop duplicates
    seen: set[int] = set()
    out: list[int] = []
    for i in indices:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _print_plan(queue: list[Task]) -> None:
    print("Plan: queued tasks")
    if not queue:
        print("  (none)")
    else:
        for i, t in enumerate(queue, start=1):
            print(f"  {i:>2}. task {t.name} -> {t.module}")
    print(f"Total tasks: {len(queue)}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    registry = discover_tasks()

    # Custom tasks registry (functions executed in-process)
    def micro_momo() -> None:
        from portfolio_exporter.scripts import micro_momo_analyzer as _mm
        import datetime as _dt
        import pathlib
        # Import lazily to keep CLI startup fast
        from tools.logbook import logbook_on_success
        # Lightweight import; used only when symbols provided
        from portfolio_exporter.core.symbols import load_alias_map, normalize_symbols

        pe_test = os.getenv("PE_TEST_MODE")
        cfg_env = os.getenv("MOMO_CFG")
        cfg_candidates = [
            cfg_env,
            "micro_momo_config.json",
            "configs/micro_momo_config.json",
            ("tests/data/micro_momo_config.json" if pe_test else None),
        ]
        cfg = next((p for p in cfg_candidates if p and os.path.exists(p)), None)
        inp = os.getenv("MOMO_INPUT") or "tests/data/meme_scan_sample.csv"
        out_dir = os.getenv("MOMO_OUT") or "out"
        argv2: list[str] = ["--input", inp, "--out_dir", out_dir]
        if cfg:
            argv2 += ["--cfg", cfg]
        chd = os.getenv("MOMO_CHAINS_DIR")
        if chd:
            argv2 += ["--chains_dir", chd]
        # symbols: env first, then memory fallback (optional), else none
        sym = os.getenv("MOMO_SYMBOLS")
        if not sym:
            try:
                from portfolio_exporter.core.memory import get_pref

                sym = get_pref("micro_momo.symbols") or ""
            except Exception:
                sym = ""
        if sym:
            # Normalize symbols using alias map (env path has priority)
            alias_map = load_alias_map([os.getenv("MOMO_ALIASES_PATH") or ""])  # type: ignore[arg-type]
            normalized = normalize_symbols(sym.split(","), alias_map)
            argv2 += ["--symbols", ",".join(normalized)]
        # Optional data mode/providers/offline passthrough via environment
        dm = os.getenv("MOMO_DATA_MODE")
        if dm:
            argv2 += ["--data-mode", dm]
        prv = os.getenv("MOMO_PROVIDERS")
        if prv:
            argv2 += ["--providers", prv]
        off = os.getenv("MOMO_OFFLINE")
        if off and off not in ("0", "false", "False"):
            argv2 += ["--offline"]
        if pe_test:
            argv2 += ["--json", "--no-files"]
        try:
            _mm.main(argv2)
        except Exception:
            # Surface failure to caller without logging success
            raise
        else:
            # On success, optionally log to logbook/worklog
            logbook_on_success(
                "micro-momo analyzer",
                scope="analyze+score+journal",
                files=["portfolio_exporter/scripts/micro_momo_analyzer.py"],
            )

    def micro_momo_go() -> None:
        from portfolio_exporter.scripts import micro_momo_go as _go
        import os as _os

        argv: list[str] = []
        pe_test = _os.getenv("PE_TEST_MODE")

        cfg_env = _os.getenv("MOMO_CFG")
        if cfg_env:
            argv += ["--cfg", cfg_env]
        else:
            for path in (
                "micro_momo_config.json",
                "config/micro_momo_config.json",
                "configs/micro_momo_config.json",
                ("tests/data/micro_momo_config.json" if pe_test else None),
            ):
                if path and _os.path.exists(path):
                    argv += ["--cfg", path]
                    break

        out_dir = _os.getenv("MOMO_OUT")
        if out_dir:
            argv += ["--out_dir", out_dir]

        providers = _os.getenv("MOMO_PROVIDERS")
        if providers:
            argv += ["--providers", providers]

        data_mode = _os.getenv("MOMO_DATA_MODE")
        if data_mode:
            argv += ["--data-mode", data_mode]

        webhook = _os.getenv("MOMO_WEBHOOK")
        if webhook:
            argv += ["--webhook", webhook]

        thread = _os.getenv("MOMO_THREAD")
        if thread:
            argv += ["--thread", thread]

        if _os.getenv("MOMO_OFFLINE") in ("1", "true", "True", "yes", "YES"):
            argv += ["--offline"]
        if _os.getenv("MOMO_AUTO_PRODUCERS") in ("1", "true", "True", "yes", "YES"):
            argv += ["--auto-producers"]
        if _os.getenv("MOMO_START_SENTINEL") in ("1", "true", "True", "yes", "YES"):
            argv += ["--start-sentinel"]

        symbols = _os.getenv("MOMO_SYMBOLS") or ""
        if not symbols:
            try:
                from portfolio_exporter.core.memory import get_pref

                symbols = get_pref("micro_momo.symbols") or ""
            except Exception:
                symbols = ""
        if symbols:
            try:
                from portfolio_exporter.core.symbols import load_alias_map, normalize_symbols

                alias_map = load_alias_map([_os.getenv("MOMO_ALIASES_PATH") or ""])
                normalized = normalize_symbols([s for s in symbols.split(",") if s.strip()], alias_map)
                if normalized:
                    argv += ["--symbols", ",".join(normalized)]
            except Exception:
                # Fallback: pass raw symbols string if normalization fails
                argv += ["--symbols", symbols]

        _go.main(argv)

    CUSTOM_TASKS: Dict[str, Callable[[], None]] = {
        "micro-momo": micro_momo,
        "momo": micro_momo,
        "micro-momo-go": micro_momo_go,
        "momo-go": micro_momo_go,
    }

    # Optional bootstrap of memory file
    if args.bootstrap_memory:
        try:
            import subprocess, sys

            cmd = [
                sys.executable,
                "-m",
                "portfolio_exporter.scripts.memory",
                "--path",
                str(args.memory_path),
                "bootstrap",
            ]
            subprocess.call(cmd)
        except Exception:
            # Non-fatal; continue without bootstrap
            pass

    if args.list_tasks:
        _print_registry(registry)
        if CUSTOM_TASKS:
            print("Custom tasks:")
            for name in sorted(CUSTOM_TASKS):
                print(f"   - {name}")
        return 0

    requested: list[str] = []
    if args.task:
        requested = [args.task]
    if args.tasks:
        requested = list(args.tasks)
    elif args.workflow:
        requested = read_workflow(args.memory_path, args.workflow)

    queue = _resolve_queue(registry, requested)

    # Add numeric selections if provided
    if args.select:
        sel = _parse_selection_expr(args.select, upper=len(registry))
        for idx in sel:
            t = registry[idx - 1]
            if t not in queue:
                queue.append(t)

    # Execute custom tasks immediately
    if requested and all(name in CUSTOM_TASKS for name in requested):
        for name in requested:
            try:
                CUSTOM_TASKS[name]()
            except Exception as exc:
                print(f"Task failed: {name}: {exc}")
                return 1
        return 0

    if args.dry_run:
        _print_plan(queue)
        return 0

    # If not a dry-run and no tasks were specified, default to just showing plan.
    if not queue:
        print("No tasks selected. Use --list-tasks or --workflow NAME.\n")
        _print_plan(queue)
        return 0

    # Execute tasks by delegating to module main() via -m in a child process.
    # We avoid importing heavy modules directly here for startup speed.
    import subprocess
    import sys

    for t in queue:
        print(f"Running task: {t.name} ({t.module})")
        cmd = [sys.executable, "-m", t.module]
        rc = subprocess.call(cmd)
        if rc != 0:
            print(f"Task failed: {t.name} (exit {rc})")
            return rc
        # Successful completion → optionally append to logbook for all tasks
        try:
            from tools.logbook import logbook_on_success as _lb

            # Map discovered task name to its script path
            script_path = f"portfolio_exporter/scripts/{t.name}.py"
            _lb(task=t.name.replace("_", "-"), scope="script run", files=[script_path])
        except Exception:
            # Logging is best-effort; never fail the task on logbook issues
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
