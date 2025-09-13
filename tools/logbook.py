from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

LOGBOOK = Path("LOGBOOK.md")
MEM = Path(".codex/memory.json")


def _load_mem() -> dict:
    if MEM.exists():
        try:
            return json.loads(MEM.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_mem(obj: dict) -> None:
    MEM.parent.mkdir(parents=True, exist_ok=True)
    MEM.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_logbook(md: str) -> None:
    if not LOGBOOK.exists():
        LOGBOOK.write_text("# Project Logbook\n\n", encoding="utf-8")
    with LOGBOOK.open("a", encoding="utf-8") as f:
        f.write(md)


def cmd_add(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    files = [s.strip() for s in (args.files or "").split(",") if s.strip()]
    interfaces_raw = [s.strip() for s in (args.interfaces or "").split(",") if s.strip()]
    interfaces: dict[str, str] = {}
    for kv in interfaces_raw:
        if ":" in kv:
            k, v = kv.split(":", 1)
            interfaces[k.strip()] = v.strip()

    # Human log (LOGBOOK.md)
    md = (
        f"### {now} • Task: {args.task} • Branch: {args.branch}\n"
        f"**Owner:** {args.owner}\n\n"
        f"**Scope:** {args.scope}\n\n"
        f"**Key files:** {', '.join(files) if files else '-'}\n\n"
        f"**Interfaces:** {json.dumps(interfaces) if interfaces else '-'}\n\n"
        f"**Status:** {args.status}\n\n"
        f"**Next:** {args.next}\n\n"
        f"**Notes:** {args.notes}\n\n"
    )
    _append_logbook(md)

    # Machine worklog (.codex/memory.json)
    mem = _load_mem()
    wl = mem.setdefault("worklog", [])
    wl.append(
        {
            "date": now,
            "task": args.task,
            "branch": args.branch,
            "owner": args.owner,
            "commit": args.commit,
            "files": files,
            "interfaces": interfaces,
            "status": args.status,
            "notes": args.notes,
        }
    )
    _save_mem(mem)
    print("Logbook and worklog updated.")
    return 0


def logbook_on_success(
    task: str,
    scope: str = "",
    files: list[str] | None = None,
    status: str = "merged",
    notes: str = "",
) -> None:
    """
    Append to LOGBOOK.md and .codex/memory.json when LOGBOOK_AUTO=1.
    No-op if LOGBOOK_AUTO is unset/false.
    """
    import subprocess  # local to keep imports light at module import time

    if str(os.getenv("LOGBOOK_AUTO", "")).lower() not in ("1", "true", "yes"):
        return
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True
        ).strip()
    except Exception:
        branch = ""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        commit = ""
    files_str = ",".join(files or [])
    # Reuse the "add" code path directly
    cmd_add(
        argparse.Namespace(
            task=task,
            branch=branch,
            owner=os.getenv("LOGBOOK_OWNER", "codex"),
            commit=commit,
            scope=scope,
            files=files_str,
            interfaces="",
            status=status,
            next="",
            notes=notes,
        )
    )


def cmd_list(_args: argparse.Namespace) -> int:
    mem = _load_mem()
    for w in mem.get("worklog", [])[-10:]:
        print(
            f"{w.get('date')}  {w.get('task')}  {w.get('status')}  {w.get('commit')}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser("logbook")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_add = sub.add_parser("add", help="append a logbook entry")
    ap_add.add_argument("--task", required=True)
    ap_add.add_argument("--branch", default=os.getenv("GIT_BRANCH", ""))
    ap_add.add_argument("--owner", default=os.getenv("LOGBOOK_OWNER", "codex"))
    ap_add.add_argument("--commit", default=os.getenv("GIT_COMMIT", ""))
    ap_add.add_argument("--scope", default="")
    ap_add.add_argument("--files", default="")  # comma-separated
    ap_add.add_argument("--interfaces", default="")  # "key:val,key2:val2"
    ap_add.add_argument("--status", default="in-progress")
    ap_add.add_argument("--next", default="")
    ap_add.add_argument("--notes", default="")
    ap_add.set_defaults(func=cmd_add)
    ap_ls = sub.add_parser("list", help="tail of machine worklog")
    ap_ls.set_defaults(func=cmd_list)

    args = ap.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
