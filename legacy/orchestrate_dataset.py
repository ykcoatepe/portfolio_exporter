import io
import os
import subprocess
import sys
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Tuple

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
OUTPUT_DIR = (
    "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_script(cmd: list[str]) -> List[str]:
    """Run a script and return the newly created files in OUTPUT_DIR."""
    out_dir = OUTPUT_DIR
    before = set(os.listdir(out_dir))
    env = os.environ.copy()
    env["OUTPUT_DIR"] = out_dir
    subprocess.run(
        [sys.executable, *cmd],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=600,  # fail fast if a script hangs >10 min
        env=env,
    )
    after = set(os.listdir(out_dir))
    new = after - before
    return [os.path.join(out_dir, f) for f in new]


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


def main() -> None:
    try:
        choice = input("Output format [csv/pdf] (default csv): ").strip().lower()
    except EOFError:
        choice = ""
    if choice == "pdf":
        fmt = "pdf"
    else:
        fmt = "csv"

    scripts = [
        ["historic_prices.py"],
        ["portfolio_greeks.py"],
        ["live_feed.py"],
        ["daily_pulse.py"],
    ]
    # Add format flag if not default
    if fmt == "pdf":
        scripts[0].append("--pdf")
        scripts[1].append("--pdf")
        scripts[2].append("--pdf")
    scripts[3].extend(["--filetype", fmt])

    files_by_script: List[Tuple[str, List[str]]] = []
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
        for cmd in scripts:
            task = progress.add_task(cmd[0], total=1)
            new_files = run_script(cmd)
            if new_files:
                files_by_script.append((cmd[0], new_files))
            progress.update(task, completed=1)  # instantly fill bar
            progress.advance(overall)
            progress.refresh()  # render once, no animation

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


if __name__ == "__main__":
    main()
