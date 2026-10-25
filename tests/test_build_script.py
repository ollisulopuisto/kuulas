"""The macOS bundle builder documents its DMG and app-only commands."""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_build_script_help_lists_the_app_only_option():
    result = subprocess.run(  # noqa: S603 -- fixed script path and literal help flag
        ["/bin/bash", str(REPO / "scripts" / "build_dmg.sh"), "--help"],
        check=False, capture_output=True, text=True)

    assert result.returncode == 0
    assert "--app-only" in result.stdout
