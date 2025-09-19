"""Assistant memory management CLI.

Provides CRUD helpers for the shared `.codex/memory.json` file used by
assistants to keep lightweight, auditable state between sessions.

The CLI matches the interface described in AGENTS.md and supports
bootstrap/validate/view/list/update/digest/rotate operations with atomic
writes and opt-in JSON output for automation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import defaultdict
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

DEFAULT_PATH = Path(".codex/memory.json")
READONLY_ENV = os.environ.get("MEMORY_READONLY", "0") == "1"

TASK_STATUSES = {"open", "in_progress", "blocked", "closed"}
QUESTION_STATUSES = {"open", "in_review", "answered", "closed"}

DEFAULT_DOCUMENT: dict[str, Any] = {
    "preferences": {},
    "workflows": {},
    "tasks": [],
    "questions": [],
    "decisions": [],
    "changelog": [],
}


class MemoryError(RuntimeError):
    """Base error for memory CLI failures."""


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    errors: list[str]


# ---------------------------------------------------------------------------
# Core I/O helpers
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_timestamp(dt: datetime | None = None) -> str:
    value = dt or utc_now()
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def expand_path(raw: str | Path | None) -> Path:
    if raw is None:
        return DEFAULT_PATH
    return Path(raw).expanduser().resolve()


def ensure_dirs(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dirs(path)
    json_text = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
    json_text += "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
        handle.write(json_text)
        handle.flush()
        os.fsync(handle.fileno())
        tmp_name = handle.name
    os.replace(tmp_name, path)


def load_document(path: Path) -> dict[str, Any]:
    if not path.exists():
        return deepcopy(DEFAULT_DOCUMENT)
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise MemoryError(f"Memory file {path} is not valid JSON") from exc
    if not isinstance(data, dict):
        raise MemoryError("Memory file must contain a JSON object")
    merged = deepcopy(DEFAULT_DOCUMENT)
    merged.update(data)
    # Ensure lists are lists; defaults otherwise.
    for key in ("tasks", "questions", "decisions", "changelog"):
        value = merged.get(key)
        if not isinstance(value, list):
            merged[key] = []
    for key in ("preferences", "workflows"):
        value = merged.get(key)
        if not isinstance(value, dict):
            merged[key] = {}
    return merged


def write_document(path: Path, document: dict[str, Any]) -> None:
    if READONLY_ENV:
        print("memory: write skipped (MEMORY_READONLY=1)")
        return
    atomic_write_json(path, document)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_document(document: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []

    for key in DEFAULT_DOCUMENT:
        if key not in document:
            errors.append(f"Missing key: {key}")

    if not isinstance(document.get("preferences"), dict):
        errors.append("preferences must be a mapping")
    if not isinstance(document.get("workflows"), dict):
        errors.append("workflows must be a mapping")

    tasks = document.get("tasks", [])
    if not isinstance(tasks, list):
        errors.append("tasks must be a list")
    else:
        for task in tasks:
            task_errors = _validate_task(task)
            errors.extend(task_errors)

    questions = document.get("questions", [])
    if not isinstance(questions, list):
        errors.append("questions must be a list")
    else:
        for question in questions:
            if not isinstance(question, dict):
                errors.append("questions entries must be objects")
                continue
            if "id" not in question or not isinstance(question["id"], int):
                errors.append("questions entries require integer id")
            status = question.get("status", "open")
            if status not in QUESTION_STATUSES:
                errors.append(f"question {question.get('id', '?')}: invalid status '{status}'")

    decisions = document.get("decisions", [])
    if not isinstance(decisions, list):
        errors.append("decisions must be a list")
    else:
        for decision in decisions:
            if not isinstance(decision, dict):
                errors.append("decisions entries must be objects")
                continue
            if "id" not in decision or not isinstance(decision["id"], int):
                errors.append("decisions entries require integer id")
            if not decision.get("title"):
                errors.append("decision entries require title")
            if not decision.get("decision"):
                errors.append("decision entries require decision text")

    changelog = document.get("changelog", [])
    if not isinstance(changelog, list):
        errors.append("changelog must be a list")
    else:
        for entry in changelog:
            if not isinstance(entry, dict):
                errors.append("changelog entries must be objects")
                continue
            if not entry.get("event"):
                errors.append("changelog entries require event")
            if not entry.get("timestamp"):
                errors.append("changelog entries require timestamp")

    return ValidationResult(ok=not errors, errors=errors)


def _validate_task(task: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(task, dict):
        return ["tasks entries must be objects"]
    if "id" not in task or not isinstance(task["id"], int):
        errors.append("task entries require integer id")
    if not task.get("title"):
        errors.append(f"task {task.get('id', '?')}: missing title")
    status = task.get("status", "open")
    if status not in TASK_STATUSES:
        errors.append(f"task {task.get('id', '?')}: invalid status '{status}'")
    labels = task.get("labels", [])
    if labels is not None and not isinstance(labels, list):
        errors.append(f"task {task.get('id', '?')}: labels must be list")
    priority = task.get("priority")
    if priority is not None and not isinstance(priority, int):
        errors.append(f"task {task.get('id', '?')}: priority must be int")
    return errors


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def parse_labels(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [label.strip() for label in raw.split(",") if label.strip()]


def next_id(entries: Iterable[dict[str, Any]]) -> int:
    max_id = 0
    for entry in entries:
        try:
            max_id = max(max_id, int(entry.get("id", 0)))
        except (TypeError, ValueError):
            continue
    return max_id + 1


def require_writable() -> None:
    if READONLY_ENV:
        print("memory: write skipped (MEMORY_READONLY=1)")
        sys.exit(0)


def parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_cutoff(raw: str) -> timedelta:
    raw = raw.strip().lower()
    if raw.endswith("d"):
        days = int(raw[:-1])
        return timedelta(days=days)
    raise MemoryError("Unsupported cutoff format; use Nd (e.g., 30d)")


def summarize_preferences(preferences: dict[str, Any]) -> str:
    if not preferences:
        return "none"
    keys = sorted(preferences.keys())
    return ", ".join(keys)


def summarize_workflows(workflows: dict[str, Any]) -> str:
    if not workflows:
        return "none"
    keys = sorted(workflows.keys())
    return ", ".join(keys)


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def cmd_bootstrap(path: Path, args: argparse.Namespace) -> int:
    document = load_document(path)
    validation = validate_document(document)
    changed = False
    if not validation.ok:
        # Replace with default document to recover.
        document = deepcopy(DEFAULT_DOCUMENT)
        changed = True

    if not path.exists():
        changed = True

    if args.session_note:
        note = args.session_note
    else:
        note = None

    changelog_entry = {
        "event": "session_start",
        "timestamp": iso_timestamp(),
    }
    if note:
        changelog_entry["details"] = note
    document.setdefault("changelog", []).append(changelog_entry)
    changed = True

    if changed and not READONLY_ENV:
        write_document(path, document)
    elif changed and READONLY_ENV:
        print("memory: write skipped (MEMORY_READONLY=1)")

    summary = build_digest(document)
    print(f"memory: ready -> {path}")
    print(f" preferences: {summarize_preferences(document['preferences'])}")
    print(f" workflows: {summarize_workflows(document['workflows'])}")
    print(
        f" open tasks: {summary['counts']['tasks_open']} | open questions: {summary['counts']['questions_open']} | decisions: {summary['counts']['decisions_total']}"
    )
    return 0


def cmd_validate(path: Path, document: dict[str, Any], args: argparse.Namespace) -> int:
    result = validate_document(document)
    payload = {"ok": result.ok, "errors": result.errors}
    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        if result.ok:
            print(f"memory: {path} validated OK")
        else:
            print(f"memory: validation failed ({len(result.errors)} error(s))")
            for err in result.errors:
                print(f" - {err}")
    return 0 if result.ok else 1


def cmd_view(path: Path, document: dict[str, Any], args: argparse.Namespace) -> int:
    if args.section:
        section = args.section
        if section not in document:
            raise MemoryError(f"Unknown section '{section}'")
        data: Any = document[section]
    else:
        data = document
    if args.json:
        print(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        ascii_text = json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True)
        print(ascii_text)
    return 0


def cmd_list_tasks(path: Path, document: dict[str, Any], args: argparse.Namespace) -> int:
    tasks: list[dict[str, Any]] = [t for t in document.get("tasks", []) if isinstance(t, dict)]
    tasks.sort(key=lambda item: item.get("id", 0))

    if args.status:
        tasks = [t for t in tasks if t.get("status") == args.status]
    if args.owner:
        tasks = [t for t in tasks if t.get("owner") == args.owner]

    if args.json:
        print(json.dumps(tasks, ensure_ascii=True, indent=2))
        return 0

    if not tasks:
        print("(no tasks)")
        return 0

    for task in tasks:
        labels = ",".join(task.get("labels", []) or [])
        priority = task.get("priority")
        owner = task.get("owner")
        status = task.get("status")
        title = task.get("title")
        line = f"[{task.get('id')}] {status} :: {title}"
        extras: list[str] = []
        if owner:
            extras.append(f"owner={owner}")
        if priority is not None:
            extras.append(f"priority={priority}")
        if labels:
            extras.append(f"labels={labels}")
        if extras:
            line += " (" + ", ".join(extras) + ")"
        print(line)
    return 0


def cmd_list_questions(path: Path, document: dict[str, Any], args: argparse.Namespace) -> int:
    questions: list[dict[str, Any]] = [q for q in document.get("questions", []) if isinstance(q, dict)]
    questions.sort(key=lambda item: item.get("id", 0))

    if args.status:
        questions = [q for q in questions if q.get("status") == args.status]
    if args.owner:
        questions = [q for q in questions if q.get("owner") == args.owner]

    if args.json:
        print(json.dumps(questions, ensure_ascii=True, indent=2))
        return 0

    if not questions:
        print("(no questions)")
        return 0

    for question in questions:
        owner = question.get("owner")
        status = question.get("status")
        text = question.get("question") or question.get("title")
        line = f"[{question.get('id')}] {status} :: {text}"
        if owner:
            line += f" (owner={owner})"
        print(line)
    return 0


def cmd_add_task(path: Path, document: dict[str, Any], args: argparse.Namespace) -> int:
    require_writable()

    task = {
        "id": next_id(document.get("tasks", [])),
        "title": args.title,
        "details": args.details or "",
        "status": "open",
        "labels": parse_labels(args.labels),
        "priority": args.priority,
        "owner": args.owner,
        "created_at": iso_timestamp(),
        "updated_at": iso_timestamp(),
    }
    document.setdefault("tasks", []).append(task)
    write_document(path, document)
    print(f"task added: {task['id']} -> {task['title']}")
    return 0


def cmd_update_task(path: Path, document: dict[str, Any], args: argparse.Namespace) -> int:
    require_writable()
    tasks: list[dict[str, Any]] = document.setdefault("tasks", [])
    selected = _find_by_id(tasks, args.id)
    if selected is None:
        raise MemoryError(f"Task {args.id} not found")

    if args.title:
        selected["title"] = args.title
    if args.status:
        if args.status not in TASK_STATUSES:
            raise MemoryError(f"Invalid status '{args.status}'")
        selected["status"] = args.status
    if args.owner is not None:
        selected["owner"] = args.owner or None
    if args.priority is not None:
        selected["priority"] = args.priority
    if args.labels is not None:
        selected["labels"] = parse_labels(args.labels)
    if args.details is not None:
        details = args.details
        if args.append:
            sep = "\n\n" if selected.get("details") else ""
            selected["details"] = f"{selected.get('details', '')}{sep}{details}"
        else:
            selected["details"] = details
    selected["updated_at"] = iso_timestamp()

    write_document(path, document)
    print(f"task updated: {selected['id']}")
    return 0


def _find_by_id(entries: Iterable[dict[str, Any]], entry_id: int) -> dict[str, Any] | None:
    for entry in entries:
        try:
            if int(entry.get("id")) == int(entry_id):
                return entry
        except (TypeError, ValueError):  # pragma: no cover - defensive
            continue
    return None


def cmd_close_task(path: Path, document: dict[str, Any], args: argparse.Namespace) -> int:
    require_writable()
    tasks: list[dict[str, Any]] = document.setdefault("tasks", [])
    task = _find_by_id(tasks, args.id)
    if task is None:
        raise MemoryError(f"Task {args.id} not found")

    task["status"] = "closed"
    if args.reason:
        sep = "\n\n" if task.get("details") else ""
        task["details"] = f"{task.get('details', '')}{sep}Closed: {args.reason}"
        task["closed_reason"] = args.reason
    task["closed_at"] = iso_timestamp()
    task["updated_at"] = iso_timestamp()

    write_document(path, document)
    print(f"task closed: {task['id']}")
    return 0


def cmd_add_decision(path: Path, document: dict[str, Any], args: argparse.Namespace) -> int:
    require_writable()
    decisions: list[dict[str, Any]] = document.setdefault("decisions", [])
    entry = {
        "id": next_id(decisions),
        "title": args.title,
        "decision": args.decision,
        "rationale": args.rationale,
        "context": args.context,
        "timestamp": iso_timestamp(),
    }
    decisions.append(entry)
    write_document(path, document)
    print(f"decision recorded: {entry['id']} -> {entry['title']}")
    return 0


def cmd_changelog(path: Path, document: dict[str, Any], args: argparse.Namespace) -> int:
    require_writable()
    event = args.event
    if event == "session-end":
        event = "session_end"
    entry = {"event": event, "timestamp": iso_timestamp()}
    if args.details:
        entry["details"] = args.details
    document.setdefault("changelog", []).append(entry)
    write_document(path, document)
    print(f"changelog appended: {event}")
    return 0


def cmd_digest(path: Path, document: dict[str, Any], args: argparse.Namespace) -> int:
    digest = build_digest(document)
    if args.json:
        print(json.dumps(digest, ensure_ascii=True, indent=2))
        return 0

    print(f"preferences: {summarize_preferences(document['preferences'])}")
    print(f"workflows: {summarize_workflows(document['workflows'])}")
    open_tasks = digest["open_tasks"]
    if open_tasks:
        print("open tasks:")
        for task in open_tasks:
            extras = []
            if task.get("owner"):
                extras.append(f"owner={task['owner']}")
            if task.get("priority") is not None:
                extras.append(f"priority={task['priority']}")
            detail = f"- [{task['id']}] {task['title']} ({task['status']})"
            if extras:
                detail += " " + " ".join(extras)
            print(detail)
    else:
        print("open tasks: none")

    open_questions = digest["open_questions"]
    if open_questions:
        print("open questions:")
        for question in open_questions:
            detail = f"- [{question['id']}] {question['question']} ({question['status']})"
            if question.get("owner"):
                detail += f" owner={question['owner']}"
            print(detail)
    else:
        print("open questions: none")

    recent_decisions = digest["recent_decisions"]
    if recent_decisions:
        print("recent decisions:")
        for decision in recent_decisions:
            print(f"- [{decision['id']}] {decision['title']}")
    else:
        print("recent decisions: none")

    print(
        "counts: tasks_total={tasks_total} open={tasks_open} questions_open={questions_open} decisions={decisions_total}".format(
            **digest["counts"]
        )
    )
    return 0


def build_digest(document: dict[str, Any]) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = [t for t in document.get("tasks", []) if isinstance(t, dict)]
    questions: list[dict[str, Any]] = [q for q in document.get("questions", []) if isinstance(q, dict)]
    decisions: list[dict[str, Any]] = [d for d in document.get("decisions", []) if isinstance(d, dict)]
    changelog: list[dict[str, Any]] = [c for c in document.get("changelog", []) if isinstance(c, dict)]

    open_tasks = [t for t in tasks if t.get("status") != "closed"]
    open_questions = [q for q in questions if q.get("status") != "closed"]

    open_tasks.sort(key=lambda item: (item.get("priority") or 999, item.get("id", 0)))
    open_questions.sort(key=lambda item: item.get("id", 0))
    decisions.sort(key=lambda item: item.get("timestamp", ""), reverse=True)

    digest = {
        "preferences": document.get("preferences", {}),
        "workflow_keys": sorted(list(document.get("workflows", {}).keys())),
        "open_tasks": [
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "status": t.get("status"),
                "owner": t.get("owner"),
                "priority": t.get("priority"),
            }
            for t in open_tasks[:10]
        ],
        "open_questions": [
            {
                "id": q.get("id"),
                "question": q.get("question") or q.get("title"),
                "status": q.get("status"),
                "owner": q.get("owner"),
            }
            for q in open_questions[:10]
        ],
        "recent_decisions": [
            {
                "id": d.get("id"),
                "title": d.get("title"),
                "timestamp": d.get("timestamp"),
            }
            for d in decisions[:5]
        ],
        "recent_changelog": [
            {"event": c.get("event"), "timestamp": c.get("timestamp")} for c in changelog[-5:]
        ],
        "counts": {
            "tasks_total": len(tasks),
            "tasks_open": len(open_tasks),
            "questions_open": len(open_questions),
            "decisions_total": len(decisions),
        },
    }
    return digest


def cmd_rotate(path: Path, document: dict[str, Any], args: argparse.Namespace) -> int:
    require_writable()
    cutoff_delta = parse_cutoff(args.cutoff)
    threshold = utc_now() - cutoff_delta

    changelog: list[dict[str, Any]] = document.get("changelog", [])
    if not changelog:
        print("changelog empty; nothing to rotate")
        return 0

    keep: list[dict[str, Any]] = []
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for entry in changelog:
        timestamp = parse_timestamp(entry.get("timestamp", ""))
        if not timestamp or timestamp >= threshold:
            keep.append(entry)
            continue
        bucket = timestamp.strftime("%Y%m")
        buckets[bucket].append(entry)

    if not buckets:
        print("no changelog entries older than cutoff")
        return 0

    for bucket, entries in buckets.items():
        rotate_path = path.with_name(f"{path.stem}.{bucket}.json")
        existing: list[dict[str, Any]] = []
        if rotate_path.exists():
            try:
                with rotate_path.open("r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                    if isinstance(loaded, list):
                        existing = loaded
            except json.JSONDecodeError:
                existing = []
        existing.extend(entries)
        existing.sort(key=lambda item: item.get("timestamp", ""))
        atomic_write_json_list(rotate_path, existing)
        print(f"rotated {len(entries)} changelog entries to {rotate_path}")

    document["changelog"] = keep
    write_document(path, document)
    return 0


def atomic_write_json_list(path: Path, entries: list[dict[str, Any]]) -> None:
    ensure_dirs(path)
    json_text = json.dumps(entries, ensure_ascii=True, indent=2, sort_keys=True)
    json_text += "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
        handle.write(json_text)
        handle.flush()
        os.fsync(handle.fileno())
        tmp_name = handle.name
    os.replace(tmp_name, path)


def cmd_format(path: Path, document: dict[str, Any], args: argparse.Namespace) -> int:
    require_writable()
    write_document(path, document)
    print(f"memory formatted: {path}")
    return 0


COMMANDS: dict[str, Callable[..., int]] = {
    "validate": cmd_validate,
    "view": cmd_view,
    "list-tasks": cmd_list_tasks,
    "list-questions": cmd_list_questions,
    "add-task": cmd_add_task,
    "update-task": cmd_update_task,
    "close-task": cmd_close_task,
    "add-decision": cmd_add_decision,
    "changelog": cmd_changelog,
    "digest": cmd_digest,
    "rotate": cmd_rotate,
    "format": cmd_format,
}


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assistant memory CLI")
    parser.add_argument("--path", default=str(DEFAULT_PATH), help="Path to memory JSON file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap", help="Ensure memory file exists and log session start")
    bootstrap.add_argument("--session-note", help="Optional note for the session_start changelog entry")

    validate = subparsers.add_parser("validate", help="Validate memory schema")
    validate.add_argument("--json", action="store_true", help="Emit JSON result")

    view = subparsers.add_parser("view", help="View memory document or a section")
    view.add_argument("--section", choices=list(DEFAULT_DOCUMENT.keys()), help="Section to display")
    view.add_argument("--json", action="store_true", help="Emit JSON output")

    list_tasks = subparsers.add_parser("list-tasks", help="List tasks with optional filters")
    list_tasks.add_argument("--status", choices=sorted(TASK_STATUSES))
    list_tasks.add_argument("--owner", help="Filter by owner")
    list_tasks.add_argument("--json", action="store_true", help="Emit JSON output")

    list_questions = subparsers.add_parser("list-questions", help="List questions with optional filters")
    list_questions.add_argument("--status", choices=sorted(QUESTION_STATUSES))
    list_questions.add_argument("--owner", help="Filter by owner")
    list_questions.add_argument("--json", action="store_true", help="Emit JSON output")

    add_task = subparsers.add_parser("add-task", help="Add a new task")
    add_task.add_argument("title")
    add_task.add_argument("--details")
    add_task.add_argument("--labels")
    add_task.add_argument("--priority", type=int)
    add_task.add_argument("--owner")

    update_task = subparsers.add_parser("update-task", help="Update an existing task")
    update_task.add_argument("id", type=int)
    update_task.add_argument("--title")
    update_task.add_argument("--details")
    update_task.add_argument("--append", action="store_true", help="Append details instead of replacing")
    update_task.add_argument("--labels", help="Comma-separated labels")
    update_task.add_argument("--priority", type=int)
    update_task.add_argument("--owner")
    update_task.add_argument("--status", choices=sorted(TASK_STATUSES))

    close_task = subparsers.add_parser("close-task", help="Close a task with optional reason")
    close_task.add_argument("id", type=int)
    close_task.add_argument("--reason")

    add_decision = subparsers.add_parser("add-decision", help="Record a decision")
    add_decision.add_argument("title")
    add_decision.add_argument("decision")
    add_decision.add_argument("--rationale")
    add_decision.add_argument("--context")

    changelog = subparsers.add_parser("changelog", help="Append a changelog entry")
    changelog.add_argument("event", help="Event name or 'session-end'")
    changelog.add_argument("--details")

    digest = subparsers.add_parser("digest", help="Summarize memory state")
    digest.add_argument("--json", action="store_true", help="Emit JSON output")

    rotate = subparsers.add_parser("rotate", help="Rotate old changelog entries")
    rotate.add_argument("--cutoff", default="30d", help="Cutoff age (e.g., 30d)")

    subparsers.add_parser("format", help="Rewrite memory file with sorted keys")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    path = expand_path(args.path)

    if args.command == "bootstrap":
        return cmd_bootstrap(path, args)

    document = load_document(path)

    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.error(f"Unknown command {args.command}")

    try:
        return handler(path, document, args)
    except MemoryError as exc:
        print(f"memory: error -> {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
