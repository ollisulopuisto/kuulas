"""The macOS bundle builder documents its DMG and app-only commands."""

import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")
assert GIT is not None


def test_build_script_help_lists_the_app_only_option():
    result = subprocess.run(  # noqa: S603 -- fixed script path and literal help flag
        ["/bin/bash", str(REPO / "scripts" / "build_dmg.sh"), "--help"],
        check=False, capture_output=True, text=True)

    assert result.returncode == 0
    assert "--app-only" in result.stdout


def test_release_build_script_help_documents_reproducible_refs():
    result = subprocess.run(  # noqa: S603 -- fixed script path and literal help flag
        ["/bin/bash", str(REPO / "scripts" / "build_release_dmg.sh"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--ref REF" in result.stdout
    assert "--podcast-commit SHA" in result.stdout
    assert "v26.10.30.2" in result.stdout


def test_release_builder_uses_pinned_podcast_worktree_and_cleans_up(tmp_path):
    kuulas = tmp_path / "kuulas"
    podcast = tmp_path / "podcast"
    kuulas.mkdir()
    (kuulas / "scripts").mkdir()
    (kuulas / "scripts" / "build_dmg.sh").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "[[ -d \"$PODCAST_SRC\" ]]\n"
        "printf '%s\\n%s\\n' \"$PODCAST_SRC\" \"$*\" > \"$BUILD_CAPTURE\"\n"
        "git -C \"$PODCAST_SRC\" rev-parse HEAD >> \"$BUILD_CAPTURE\"\n",
        encoding="utf-8",
    )
    (kuulas / "scripts" / "build_dmg.sh").chmod(0o755)
    release_builder = kuulas / "scripts" / "build_release_dmg.sh"
    release_builder.write_bytes((REPO / "scripts" / "build_release_dmg.sh").read_bytes())
    release_builder.chmod(0o755)
    podcast.mkdir()
    init_repo(kuulas)
    commit(kuulas, "kuulas fixture")
    init_repo(podcast)
    remote_podcast = tmp_path / "podcast-origin"
    remote_podcast.mkdir()
    init_repo(remote_podcast)
    (remote_podcast / "package.txt").write_text(
        "pinned podcast source\n", encoding="utf-8"
    )
    commit(remote_podcast, "podcast fixture")
    git(remote_podcast, "branch", "-M", "main")
    podcast_sha = git(remote_podcast, "rev-parse", "HEAD")
    git(podcast, "remote", "add", "origin", str(remote_podcast))

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name, body in {
        "uname": (
            "#!/bin/sh\n"
            "case \"$1\" in -s) printf 'Darwin\\n' ;; "
            "-m) printf 'arm64\\n' ;; esac\n"
        ),
        "xcodebuild": "#!/bin/sh\nprintf 'Xcode 26.3\\n'\n",
        "uv": "#!/bin/sh\nprintf 'uv 0.13.6\\n'\n",
    }.items():
        executable = fake_bin / name
        executable.write_text(body, encoding="utf-8")
        executable.chmod(0o755)

    capture = tmp_path / "capture.txt"
    output = tmp_path / "dist"
    env = os.environ.copy()
    env.update(
        PATH=f"{fake_bin}:{env['PATH']}",
        PODCAST_REPO=str(podcast),
        BUILD_CAPTURE=str(capture),
    )
    result = subprocess.run(  # noqa: S603 -- fixed script and constructed fixture arguments
        [
            "/bin/bash",
            str(release_builder),
            "--podcast-commit",
            podcast_sha,
            "--out",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    lines = capture.read_text(encoding="utf-8").splitlines()
    assert Path(lines[0]).name == "podcast"
    assert lines[1] == f"--out {output}"
    assert lines[2] == podcast_sha
    assert not Path(lines[0]).exists()
    assert git(podcast, "status", "--porcelain") == ""


def init_repo(path: Path) -> None:
    git(path, "init", "-q")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.com")


def commit(path: Path, message: str) -> None:
    git(path, "add", ".")
    git(path, "commit", "-qm", message)


def git(path: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603 -- fixed git command with test fixture paths
        [GIT, "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
