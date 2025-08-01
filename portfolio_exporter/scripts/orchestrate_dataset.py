import io
import os
import zipfile
from datetime import datetime
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
os.makedirs(OUTPUT_DIR, exist_ok=True)


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

        # Save the title page to a BytesIO object
        title_page_pdf = io.BytesIO(pdf.output(dest="S").encode("latin-1"))
        merger.append(title_page_pdf)

        # Add bookmark for the title page
        merger.add_outline_item(clean_title, len(merger.pages) - 1)

        for path in pdfs:
            merger.append(path)
    merger.write(dest)
    merger.close()


def create_zip(files: List[str], dest: str) -> None:
    """Create a zip archive containing the given files."""
    with zipfile.ZipFile(dest, "w") as zf:
        for path in files:
            zf.write(path, os.path.basename(path))


def cleanup(files: List[str]) -> None:
    """Delete the given files, ignoring missing paths."""
    for path in files:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def run(fmt: str = "csv") -> None:
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
        console.print("[yellow]No files generated; exiting batch.")
        return
    ts = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y%m%d_%H%M")
    all_files = [f for _, file_list in files_by_script for f in file_list]
    if fmt == "pdf":
        dest = os.path.join(OUTPUT_DIR, f"dataset_{ts}.pdf")
        merge_pdfs(files_by_script, dest)
    else:
        dest = os.path.join(OUTPUT_DIR, f"dataset_{ts}.zip")
        create_zip(all_files, dest)

    cleanup(all_files)
    print(f"Created {dest}")

    if failed:
        print(f"⚠ Batch finished with {len(failed)} failure(s):", failed)
    else:
        print("✅ Overnight batch completed – all files written.")
