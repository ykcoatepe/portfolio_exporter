from __future__ import annotations

from pathlib import Path

from tools.logbook import main as log_main


def test_logbook_add_and_list(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    rc = log_main(
        [
            "add",
            "--task",
            "sample",
            "--branch",
            "dev",
            "--owner",
            "codex",
            "--commit",
            "abc",
            "--scope",
            "x",
            "--files",
            "a.py,b.py",
            "--interfaces",
            "foo:1,bar:2",
            "--status",
            "merged",
            "--next",
            "y",
            "--notes",
            "ok",
        ]
    )
    assert rc == 0
    assert (tmp_path / ".codex/memory.json").exists()
    assert (tmp_path / "LOGBOOK.md").exists()
    rc2 = log_main(["list"])  # noqa: F841
    out = capsys.readouterr().out
    assert "sample" in out

