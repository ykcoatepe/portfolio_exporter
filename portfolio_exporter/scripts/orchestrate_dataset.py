import io
import os
import sys
import zipfile
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Tuple
from zoneinfo import ZoneInfo

from portfolio_exporter.core.config import settings

from fpdf import FPDF
from pypdf import PdfWriter
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.console import Console

# Directory where orchestrated dataset and script outputs are stored.
OUTPUT_DIR = os.path.expanduser(settings.output_dir)


def run_script(func: Callable[[], None]) -> List[str]:
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


def merge_pdfs(files_by_script: List[Tuple[str, List[str]]], dest: str) -> None:
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


def create_zip(files: List[str], dest: str | Path) -> tuple[int, list[str]]:
    """Create a zip archive containing the given files, skipping missing.

    Returns
    -------
    (added_count, missing_list)
    """
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    added = 0
    missing: list[str] = []
    with zipfile.ZipFile(dest_path, "w") as zf:
        for p in files:
            path = Path(p)
            if path.exists():
                zf.write(path, arcname=path.name)
                added += 1
            else:
                missing.append(str(path))
    return added, missing


def cleanup(files: List[str]) -> None:
    """Delete the given files, ignoring missing paths."""
    for path in files:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def run(fmt: str = "csv", strict: bool = False, no_pretty: bool = False) -> tuple[str, int, list[str]] | None:
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

    files_by_script: List[Tuple[str, List[str]]] = []
    failed: list[str] = []
    console = Console(
        force_terminal=True
    )  # force Rich to treat IDE/CI output as a real TTY
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
    args = parser.parse_args()

    result = run(fmt=args.format, strict=args.strict, no_pretty=args.no_pretty)
    if args.strict and result is not None:
        _, _, missing = result
        if missing:
            sys.exit(2)


if __name__ == "__main__":
    main()
