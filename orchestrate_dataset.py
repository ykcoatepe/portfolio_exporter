import os
import subprocess
import sys
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List

from historic_prices import OUTPUT_DIR


def run_script(cmd: list[str]) -> List[str]:
    """Run a script and return newly created files in OUTPUT_DIR."""
    before = set(os.listdir(OUTPUT_DIR))
    subprocess.run([sys.executable, *cmd], check=True)
    after = set(os.listdir(OUTPUT_DIR))
    return [os.path.join(OUTPUT_DIR, f) for f in after - before]


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
    files: List[str] = []
    files += run_script(["historic_prices.py", *flag])
    files += run_script(["portfolio_greeks.py", *flag])
    files += run_script(["live_feed.py", *flag])
    files += run_script(["daily_pulse.py", "--filetype", fmt])

    ts = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y%m%d_%H%M")
    dest = os.path.join(OUTPUT_DIR, f"dataset_{ts}.zip")
    create_zip(files, dest)
    cleanup(files)
    print(f"Created {dest}")


if __name__ == "__main__":
    main()
