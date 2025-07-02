from __future__ import annotations

import io
import os
import io
import os
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from fpdf import FPDF
from pypdf import PdfWriter

OUTPUT_DIR = "."


def get_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def run_script(cmd: List[str], *, env=None) -> List[str]:
    out_dir = OUTPUT_DIR
    before = set(os.listdir(out_dir))
    subprocess.run(
        [sys.executable, *cmd],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=600,
        stdin=subprocess.DEVNULL,
        env=env,
    )
    after = set(os.listdir(out_dir))
    new = after - before
    return [os.path.join(out_dir, f) for f in new]


def create_zip(files: List[str], dest: str) -> None:
    with zipfile.ZipFile(dest, "w") as zf:
        for p in files:
            zf.write(p, os.path.basename(p))


def cleanup(files: Iterable[str]) -> None:
    for p in files:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def merge_pdfs(files_by_script: List[Tuple[str, List[str]]], dest: str) -> None:
    merger = PdfWriter()

    # cover page
    cover = FPDF()
    cover.add_page()
    cover.set_font("Helvetica", "B", 32)
    cover.cell(0, 100, "Dataset", 0, 1, "C")
    merger.append(io.BytesIO(cover.output(dest="S").encode("latin-1")))

    for title, files in files_by_script:
        pdfs = [p for p in files if p.lower().endswith(".pdf")]
        if not pdfs:
            continue
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 24)
        pdf.cell(0, 100, title.replace("_", " ").title(), 0, 1, "C")
        title_buf = io.BytesIO(pdf.output(dest="S").encode("latin-1"))
        merger.append(title_buf)
        merger.add_outline_item(title, len(merger.pages) - 1)
        for p in pdfs:
            merger.append(p)

    # closing page
    end = FPDF()
    end.add_page()
    end.set_font("Helvetica", size=12)
    end.cell(0, 20, "End of Dataset", 0, 1, "C")
    merger.append(io.BytesIO(end.output(dest="S").encode("latin-1")))

    merger.write(dest)
    merger.close()


def main() -> None:
    fmt = (
        input("Enter output format (csv or pdf, default csv): ").strip().lower()
        or "csv"
    )
    scripts = [
        ["pulse.py"],
        ["live.py"],
        ["options.py"],
    ]
    files_by_script: List[Tuple[str, List[str]]] = []
    for cmd in scripts:
        new = run_script(cmd)
        if new:
            files_by_script.append((Path(cmd[0]).stem, new))
    all_files = [f for _, lst in files_by_script for f in lst]
    if fmt == "pdf":
        dest = os.path.join(OUTPUT_DIR, f"dataset_{get_timestamp()}.pdf")
        merge_pdfs(files_by_script, dest)
    else:
        dest = os.path.join(OUTPUT_DIR, f"dataset_{get_timestamp()}.zip")
        create_zip(all_files, dest)
    cleanup(all_files)


if __name__ == "__main__":
    main()
