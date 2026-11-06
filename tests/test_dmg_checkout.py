"""The macOS build checks out package sources without case-colliding agent notes."""

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_podcast_checkout_excludes_notes_and_preserves_build_sources(tmp_path):
    workflow = (ROOT / ".github/workflows/dmg.yml").read_text()
    block = workflow.split("repository: ollisulopuisto/podcast", 1)[1].split(
        "- uses:", 1)[0]
    match = re.search(r"sparse-checkout: \|\n((?: +[^\n]+\n)+)", block)
    paths = [line.strip() for line in match[1].splitlines()] if match else []
    repo = tmp_path / "podcast"
    repo.mkdir()

    def git(*args):
        return subprocess.run(  # noqa: S603 - fixed fixture-only Git commands, no shell
            [shutil.which("git"), "-C", str(repo), *args], check=True,
            capture_output=True, text=True).stdout

    git("init")
    for name in ("packages/wordalign/src/wordalign.py", "apps/automixer/main.py",
                 ".jules/palette.md", "pyproject.toml"):
        file = repo / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("source\n")
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.org",
        "commit", "-m", "fixture")
    if paths:
        git("sparse-checkout", "init", "--cone")
        git("sparse-checkout", "set", *paths)
    assert not (repo / ".jules").exists(), "Agent notes collide by case on macOS"
    assert (repo / "packages/wordalign/src/wordalign.py").is_file()
    assert (repo / "apps/automixer/main.py").is_file()
    assert (repo / "pyproject.toml").is_file()
    assert git("status", "--porcelain") == ""
