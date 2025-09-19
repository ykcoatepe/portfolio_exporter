import io
import os
import socket
import sys
import zipfile
from argparse import ArgumentParser
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fpdf import FPDF
from pypdf import PdfWriter
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from portfolio_exporter.core.config import settings

# Directory where orchestrated dataset and script outputs are stored.
OUTPUT_DIR = os.path.expanduser(settings.output_dir)

# Cache for preflight results within this process/session
_PREFLIGHT_CACHE: dict | None = None


def run_script(func: Callable[[], None]) -> list[str]:
    """Run a script callable and return new or modified files in OUTPUT_DIR."""
    out_dir = OUTPUT_DIR
    before_mtimes: dict[str, float] = {}
    for fname in os.listdir(out_dir):
        path = os.path.join(out_dir, fname)
        try:
            before_mtimes[fname] = os.path.getmtime(path)
        except OSError:
            before_mtimes[fname] = 0.0
    func()
    files_out: list[str] = []
    for fname in os.listdir(out_dir):
        path = os.path.join(out_dir, fname)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        prev = before_mtimes.get(fname)
        if prev is None or mtime > prev:
            files_out.append(path)
    return files_out


def merge_pdfs(files_by_script: list[tuple[str, list[str]]], dest: str) -> None:
    """Merge the given PDF files into a single output, adding bookmarks for each script and title pages, skipping non-PDF files."""
    merger = PdfWriter()
    for title, files in files_by_script:
        pdfs = [path for path in files if path.lower().endswith(".pdf")]
        if not pdfs:
            continue

        clean_title = title.replace("_", " ").replace(".py", "").title()

        # Create a title page using FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 24)
        pdf.cell(0, 100, clean_title, 0, 1, "C")

        # Save the title page to a BytesIO object and rewind for reading
        title_page_pdf = io.BytesIO(pdf.output(dest="S").encode("latin-1"))
        try:
            title_page_pdf.seek(0)
        except Exception:
            pass  # defensive: BytesIO should support seek(0)
        merger.append(title_page_pdf)

        # Add bookmark for the title page
        merger.add_outline_item(clean_title, len(merger.pages) - 1)

        for path in pdfs:
            merger.append(path)
    merger.write(dest)
    merger.close()


def create_zip(files: list[str], dest: str | Path) -> tuple[int, list[str]]:
    """Create a zip archive containing the given files, skipping missing.

    - De-duplicates input paths while preserving order to avoid duplicate
      entries in the ZIP when multiple scripts touched the same file.

    Returns
    -------
    (added_count, missing_list)
    """
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    added = 0
    missing: list[str] = []
    # Deduplicate by absolute path while preserving order
    seen_paths: set[str] = set()
    unique_files: list[Path] = []
    for p in files:
        path = Path(p).resolve()
        sp = str(path)
        if sp in seen_paths:
            continue
        seen_paths.add(sp)
        unique_files.append(path)
    with zipfile.ZipFile(dest_path, "w") as zf:
        for path in unique_files:
            if path.exists():
                # Use basename; duplicates are avoided by unique_files above
                zf.write(path, arcname=path.name)
                added += 1
            else:
                missing.append(str(path))
    return added, missing


def cleanup(files: list[str]) -> None:
    """Delete the given files, ignoring missing paths."""
    for path in files:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def run(
    fmt: str = "csv",
    strict: bool = False,
    no_pretty: bool = False,
    expect: list[str] | None = None,
) -> tuple[str, int, list[str]] | None:
    fmt = fmt.lower()

    from portfolio_exporter.scripts import (
        daily_pulse,
        historic_prices,
        live_feed,
        portfolio_greeks,
    )

    scripts: list[tuple[str, Callable[[], None]]] = [
        ("historic_prices", lambda: historic_prices.run(fmt=fmt)),
        ("portfolio_greeks", lambda: portfolio_greeks.run(fmt=fmt)),
        (
            "live_feed",
            (lambda: live_feed.run() if fmt == "csv" else live_feed.run(fmt=fmt)),
        ),
        ("daily_pulse", lambda: daily_pulse.run(fmt=fmt)),
    ]

    files_by_script: list[tuple[str, list[str]]] = []
    failed: list[str] = []
    # Honor PE_QUIET by routing progress output to a sink
    quiet_env = os.getenv("PE_QUIET") not in (None, "", "0")
    if quiet_env:
        console = Console(file=io.StringIO(), force_terminal=False)
    else:
        console = Console(force_terminal=True)  # treat IDE/CI as TTY for richer output
    progress = Progress(
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TextColumn("{task.description}"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
        auto_refresh=False,  # no automatic animation
    )
    with progress:
        overall = progress.add_task("overall", total=len(scripts))
        for name, func in scripts:
            task = progress.add_task(name, total=1)
            try:
                new_files = run_script(func)
            except Exception as error:
                console.print(f"[red]Error running {name}: {error}")
                failed.append(name)
                new_files = []
            if new_files:
                files_by_script.append((name, new_files))
            progress.update(task, completed=1)  # instantly fill bar
            progress.advance(overall)
            progress.refresh()  # render once, no animation

    if not files_by_script:
        if os.getenv("PE_QUIET"):
            # Keep silent except for essential one-liner
            print("No files generated; exiting batch.")
        else:
            console.print("[yellow]No files generated; exiting batch.")
        return None
    ts = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y%m%d_%H%M")
    all_files = [f for _, file_list in files_by_script for f in file_list]
    # If expectations were provided, include them in the zip attempt to make
    # strict mode deterministic even as scripts evolve.
    if expect:
        exp_paths: list[str] = []
        for item in expect:
            p = Path(item)
            if not p.is_absolute():
                p = Path(OUTPUT_DIR) / p
            exp_paths.append(str(p))
        # Deduplicate while preserving order
        seen = set()
        combined: list[str] = []
        for x in list(all_files) + exp_paths:
            if x not in seen:
                seen.add(x)
                combined.append(x)
        all_files = combined
    if fmt == "pdf":
        dest = os.path.join(OUTPUT_DIR, f"dataset_{ts}.pdf")
        merge_pdfs(files_by_script, dest)
        cleanup(all_files)
        print(f"Created {dest}")
        if failed:
            print(f"⚠ Batch finished with {len(failed)} failure(s):", failed)
        else:
            print("✅ Overnight batch completed – all files written.")
        return dest, 0, []
    else:
        dest = os.path.join(OUTPUT_DIR, f"dataset_{ts}.zip")
        added_count, missing_list = create_zip(all_files, dest)
        cleanup(all_files)

        # Summaries
        print(f"Zipped {added_count} file(s) → {dest}")
        quiet = bool(os.getenv("PE_QUIET"))
        if missing_list:
            # Prefer Rich pretty table when allowed
            if not quiet and not no_pretty:
                try:
                    from rich.table import Table

                    tbl = Table(title="Missing files", show_header=True)
                    tbl.add_column("Path")
                    limit = 30
                    shown = 0
                    for path in missing_list[:limit]:
                        tbl.add_row(path)
                        shown += 1
                    if len(missing_list) > limit:
                        tbl.add_row(f"+{len(missing_list) - limit} more…")
                    Console().print(tbl)
                except Exception:
                    # Fallback to plain warnings on any Rich issues
                    for path in missing_list:
                        print(f"WARN missing file: {path}")
            else:
                for path in missing_list:
                    print(f"WARN missing file: {path}")

            # One-liner summary of skipped files
            print(f"Skipped {len(missing_list)} missing; see list above")

        if failed:
            print(f"⚠ Batch finished with {len(failed)} failure(s):", failed)
        else:
            print("✅ Overnight batch completed – all files written.")

        # Strict mode: non-zero exit if any expected files were missing
        if strict and missing_list:
            # When used via CLI, caller may interpret this. When invoked from menu,
            # strict is False by default to keep behavior non-breaking.
            # Return info so main() can sys.exit(2).
            return dest, added_count, missing_list
        return dest, added_count, missing_list


def _print_preflight_summary(report: dict, no_pretty: bool) -> None:
    quiet = bool(os.getenv("PE_QUIET"))
    if quiet:
        # single line summary
        csv_bad = sum(1 for c in report["recent_csv_checks"] if c["ok"] is False)
        print(
            f"Pre-flight: outdir={'OK' if report['output_dir_writable'] else 'NO'}; "
            f"csv_bad={csv_bad}; ibkr={report['ibkr_socket_ok']}"
        )
        for w in report["warnings"]:
            print(f"WARN: {w}")
        for e in report["errors"]:
            print(f"ERROR: {e}")
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()

        # Imports table
        t_imp = Table(title="Imports", show_header=True)
        t_imp.add_column("Package")
        t_imp.add_column("Status")
        for pkg, ok in report["imports"].items():
            t_imp.add_row(pkg, "✅" if ok else "⚠️")
        if not no_pretty:
            console.print(t_imp)

        # CSV checks table
        t_csv = Table(title="Recent CSV checks", show_header=True)
        t_csv.add_column("Name")
        t_csv.add_column("Exists")
        t_csv.add_column("Missing cols")
        for c in report["recent_csv_checks"]:
            miss = ", ".join(c["missing_cols"]) if c["missing_cols"] else ""
            t_csv.add_row(c["name"], "yes" if c["exists"] else "no", miss)
        if not no_pretty:
            console.print(t_csv)

        # One-liner statuses
        console.print(f"Output dir writable: {'yes' if report['output_dir_writable'] else 'no'}")
        if report["ibkr_socket_ok"] is not None:
            console.print(f"IBKR socket reachable: {'yes' if report['ibkr_socket_ok'] else 'no'}")

        # Warnings/errors plainly listed
        for w in report["warnings"]:
            console.print(f"[yellow]WARN[/]: {w}")
        for e in report["errors"]:
            console.print(f"[red]ERROR[/]: {e}")
    except Exception:
        # Fallback plain text
        csv_bad = sum(1 for c in report["recent_csv_checks"] if c["ok"] is False)
        print(
            f"Pre-flight: outdir={'OK' if report['output_dir_writable'] else 'NO'}; "
            f"csv_bad={csv_bad}; ibkr={report['ibkr_socket_ok']}"
        )
        for w in report["warnings"]:
            print(f"WARN: {w}")
        for e in report["errors"]:
            print(f"ERROR: {e}")


def preflight_check(no_pretty: bool = False) -> dict:
    """
    Perform lightweight environment checks and optional CSV sanity checks.
    Returns a report dict with fields described in the CLI prompt.
    """
    global _PREFLIGHT_CACHE
    if _PREFLIGHT_CACHE is not None:
        # Reuse previous result to avoid repeated socket probes; still print summary.
        _print_preflight_summary(_PREFLIGHT_CACHE, no_pretty=no_pretty)
        return _PREFLIGHT_CACHE

    report: dict = {
        "output_dir_writable": False,
        "imports": {
            "pandas": False,
            "yfinance": False,
            "reportlab": False,
            "ib_insync": False,
        },
        "ibkr_socket_ok": None,
        "recent_csv_checks": [],
        "errors": [],
        "warnings": [],
    }

    # Output dir writable check
    outdir = Path(os.path.expanduser(settings.output_dir))
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        probe = outdir / ".pe_preflight_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        report["output_dir_writable"] = True
    except Exception as exc:  # pragma: no cover - depends on FS permissions
        report["output_dir_writable"] = False
        report["errors"].append(f"Output directory not writable: {outdir} ({exc})")

    # Imports
    try:
        import pandas as _p  # noqa: F401

        report["imports"]["pandas"] = True
    except Exception:
        report["warnings"].append("Optional dependency missing: pandas")
    try:
        import yfinance as _y  # noqa: F401

        report["imports"]["yfinance"] = True
    except Exception:
        report["warnings"].append("Optional dependency missing: yfinance")
    try:
        import reportlab as _r  # noqa: F401

        report["imports"]["reportlab"] = True
    except Exception:
        report["warnings"].append("Optional dependency missing: reportlab")
    try:
        import ib_insync as _ib  # noqa: F401

        report["imports"]["ib_insync"] = True
    except Exception:
        report["warnings"].append("Optional dependency missing: ib_insync")

    # IBKR socket check (best-effort)
    if report["imports"]["ib_insync"]:
        try:
            with socket.create_connection(("127.0.0.1", 7496), timeout=0.25):
                pass
            report["ibkr_socket_ok"] = True
        except Exception:
            report["ibkr_socket_ok"] = False
            report["warnings"].append("IBKR TWS/Gateway not reachable on 127.0.0.1:7496 (use 7497 for paper)")

    # CSV header sanity checks (best-effort)
    from portfolio_exporter.core import io as io_core

    checks = [
        ("portfolio_greeks_positions", {"underlying", "right", "strike", "expiry", "qty"}),
        ("live_quotes", {"symbol", "bid", "ask"}),
    ]
    for name, expected in checks:
        path = io_core.latest_file(name, "csv")
        entry = {
            "name": name,
            "path": str(path) if path else "",
            "exists": bool(path),
            "ok": None,
            "missing_cols": [],
        }
        if path and Path(path).exists():
            try:
                # minimal header reader without pandas dependency
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    header = fh.readline().strip().split(",")
                present = {h.strip().strip('"').lower() for h in header if h}
                missing = sorted(col for col in expected if col not in present)
                entry["missing_cols"] = missing
                entry["ok"] = len(missing) == 0
                if missing:
                    report["warnings"].append(f"CSV {name} missing columns: {', '.join(missing)}")
            except Exception as exc:  # pragma: no cover - unexpected format
                entry["ok"] = None
                report["warnings"].append(f"Could not read CSV {name}: {exc}")
        report["recent_csv_checks"].append(entry)

    # Pretty output
    _PREFLIGHT_CACHE = report
    _print_preflight_summary(report, no_pretty=no_pretty)
    return report


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--format", choices=["csv", "excel", "pdf"], default="csv")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit with code 2 if any expected file is missing",
    )
    parser.add_argument(
        "--no-pretty",
        action="store_true",
        help="disable Rich tables even on TTY",
    )
    parser.add_argument(
        "--expect",
        metavar="JSON",
        help='path to JSON list or {"files":[...]} of expected output files',
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="run environment and CSV sanity checks only",
    )
    parser.add_argument(
        "--preflight-strict",
        action="store_true",
        help="non-zero exit if any preflight error or CSV issue",
    )
    args = parser.parse_args()

    if args.preflight:
        report = preflight_check(no_pretty=args.no_pretty)
        if args.preflight_strict:
            any_error = bool(report["errors"]) or any(
                c.get("ok") is False for c in report["recent_csv_checks"]
            )
            if any_error:
                sys.exit(2)
        sys.exit(0)

    # Optional: expected outputs JSON to augment zip list
    expect: list[str] | None = None
    if hasattr(args, "expect") and args.expect:
        try:
            import json

            with open(args.expect, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and "files" in data and isinstance(data["files"], list):
                expect = [str(x) for x in data["files"]]
            elif isinstance(data, list):
                expect = [str(x) for x in data]
        except Exception as exc:
            print(f"WARN could not read --expect file: {exc}")

    result = run(
        fmt=args.format,
        strict=args.strict,
        no_pretty=args.no_pretty,
        expect=expect,
    )
    if args.strict and result is not None:
        _, _, missing = result
        if missing:
            sys.exit(2)


if __name__ == "__main__":
    main()
