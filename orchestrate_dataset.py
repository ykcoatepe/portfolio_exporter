import os
import subprocess
import sys
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Tuple

from pypdf import PdfWriter
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.console import Console

from historic_prices import OUTPUT_DIR


def run_script(cmd: list[str]) -> List[str]:
    """Run a script and return newly created files in OUTPUT_DIR."""
    before = set(os.listdir(OUTPUT_DIR))
    subprocess.run(
        [sys.executable, *cmd],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=600,  # fail fast if a script hangs >10 min
    )
    after = set(os.listdir(OUTPUT_DIR))
    return [os.path.join(OUTPUT_DIR, f) for f in after - before]


def merge_pdfs(files_by_script: List[Tuple[str, List[str]]], dest: str) -> None:
    """Merge the given PDF files into a single file, adding bookmarks for each script."""
    merger = PdfWriter()
    for title, files in files_by_script:
        if not files:
            continue
        page_number = len(merger.pages)
        clean_title = title.replace("_", " ").replace(".py", "").title()
        merger.add_outline_item(clean_title, page_number)
        for path in files:
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
    fmt = "pdf" if choice == "pdf" else "csv"

    flag = ["--pdf"] if fmt == "pdf" else []
    scripts = [
        ["historic_prices.py", *flag],
        ["portfolio_greeks.py", *flag],
        ["live_feed.py", *flag],
        ["daily_pulse.py", "--filetype", fmt],
    ]

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
