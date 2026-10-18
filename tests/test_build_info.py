"""The build label: which version and commit a bug report is about."""

import subprocess

from kuulas import build_info


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path, version="26.10.18.64"):
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "kuulas"\nversion = "{version}"\n')
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "x")
    return tmp_path


def test_label_is_version_and_commit(tmp_path):
    repo = _repo(tmp_path)
    label = build_info.build_label(repo)
    assert label.startswith("v26.10.18.64+")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo,
                          capture_output=True, text=True, check=True).stdout.strip()
    assert label == f"v26.10.18.64+{head}"


def test_uncommitted_changes_are_marked(tmp_path):
    repo = _repo(tmp_path)
    (repo / "new.txt").write_text("x")
    assert build_info.build_label(repo).endswith("+dirty")


def test_without_git_it_is_the_version_alone(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "26.10.18.7"\n')
    assert build_info.build_label(tmp_path) == "v26.10.18.7"


def test_unreadable_everything_is_unknown(tmp_path):
    assert build_info.build_label(tmp_path / "nowhere") == "unknown"
