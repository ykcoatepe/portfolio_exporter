import os
import pathlib
import subprocess
import sys


def test_cli_exit_zero(tmp_path: pathlib.Path) -> None:
    cmd = [sys.executable, "-m", "main", "--quiet"]
    proc = subprocess.run(cmd, input="0\n", text=True)
    assert proc.returncode == 0
