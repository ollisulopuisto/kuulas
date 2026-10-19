"""Where the UI files are: in a bundle or the repo (WP73)."""

from __future__ import annotations

from pathlib import Path

from kuulas import server
from kuulas.paths import find_ui_dir


def make_ui(folder: Path) -> Path:
    folder.mkdir(parents=True)
    (folder / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return folder


def module(root: Path, *parts: str) -> Path:
    """A fake ``kuulas/paths.py`` at ``root/<parts>/kuulas/paths.py``."""
    file = root.joinpath(*parts, "kuulas", "paths.py")
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("", encoding="utf-8")
    return file


def test_repo_checkout_uses_the_ui_folder_at_the_repo_root(tmp_path):
    file = module(tmp_path, "src")
    ui = make_ui(tmp_path / "ui")
    assert find_ui_dir(file) == ui


def test_bundle_uses_the_ui_folder_beside_the_package(tmp_path):
    # Briefcase copies each source folder into Resources/app: app/kuulas and app/ui.
    file = module(tmp_path, "Resources", "app")
    ui = make_ui(tmp_path / "Resources" / "app" / "ui")
    assert find_ui_dir(file) == ui


def test_installed_wheel_uses_the_ui_folder_inside_the_package(tmp_path):
    file = module(tmp_path, "site-packages")
    ui = make_ui(file.parent / "ui")
    assert find_ui_dir(file) == ui


def test_inside_the_package_wins_over_the_repo_folder(tmp_path):
    file = module(tmp_path, "src")
    inside = make_ui(file.parent / "ui")
    make_ui(tmp_path / "ui")
    assert find_ui_dir(file) == inside


def test_a_folder_without_index_html_is_skipped(tmp_path):
    file = module(tmp_path, "src")
    (file.parent / "ui").mkdir()
    repo_ui = make_ui(tmp_path / "ui")
    assert find_ui_dir(file) == repo_ui


def test_nothing_found_returns_the_repo_guess_so_the_server_reports_it(tmp_path):
    file = module(tmp_path, "src")
    assert find_ui_dir(file) == tmp_path / "ui"


def test_the_real_ui_dir_is_found_from_this_checkout():
    assert (server.UI_DIR / "index.html").is_file()
