"""The desktop window's native clipboard (WP76): the page copies the shown time with it
when the web view blocks navigator.clipboard."""

from __future__ import annotations

from pathlib import Path

import pytest

from kuulas.desktop import Bridge, clipboard_command


def test_clipboard_command_per_platform():
    assert clipboard_command("darwin") == ["pbcopy"]
    assert clipboard_command("win32") == ["clip"]
    assert clipboard_command("linux")[0] == "xclip"


def test_copy_text_pipes_the_text_to_the_command(tmp_path: Path):
    bridge = Bridge(None, tmp_path)
    got: list[tuple[list[str], str]] = []
    bridge._copier = lambda command, text: got.append((command, text))
    assert bridge.copy_text("0:08,938") is True
    assert got[0][1] == "0:08,938"
    assert got[0][0] == clipboard_command()


def test_copy_text_refuses_non_text_and_long_text(tmp_path: Path):
    bridge = Bridge(None, tmp_path)
    bridge._copier = lambda command, text: pytest.fail("must not run")
    assert bridge.copy_text(None) is False  # type: ignore[arg-type]
    assert bridge.copy_text("x" * 1000) is False


def test_copy_text_reports_a_missing_program(tmp_path: Path):
    bridge = Bridge(None, tmp_path)

    def missing(command, text):
        raise FileNotFoundError(command[0])

    bridge._copier = missing
    assert bridge.copy_text("1") is False
