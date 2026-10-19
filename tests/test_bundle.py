"""The parts of the app bundle that run without a bundle (WP73): environment, logs,
the baked-in build label and the headless ``--selftest``."""

from __future__ import annotations

import os
from pathlib import Path

from kuulas import build_info, bundle, cli, selftest


def fake_bundle(tmp_path: Path) -> Path:
    """``Kuulas.app/Contents/Resources`` with ``app/kuulas`` and ``bin``."""
    resources = tmp_path / "Kuulas.app" / "Contents" / "Resources"
    (resources / "app" / "kuulas").mkdir(parents=True)
    (resources / "bin").mkdir()
    return resources


def test_resources_dir_is_found_only_inside_a_bundle(tmp_path):
    resources = fake_bundle(tmp_path)
    module = resources / "app" / "kuulas" / "bundle.py"
    assert bundle.resources_dir(module) == resources
    assert bundle.resources_dir(tmp_path / "src" / "kuulas" / "bundle.py") is None


def test_the_bundled_bin_comes_first_on_path(tmp_path):
    resources = fake_bundle(tmp_path)
    got = bundle.environment(resources, {"PATH": "/usr/bin:/bin"}, tmp_path / "home")
    assert got["PATH"].split(os.pathsep)[:3] == [
        str(resources / "bin"), "/usr/bin", "/bin"]


def test_path_is_set_even_when_the_app_starts_without_one(tmp_path):
    resources = fake_bundle(tmp_path)
    got = bundle.environment(resources, {}, tmp_path / "home")
    assert got["PATH"].split(os.pathsep)[0] == str(resources / "bin")


def test_numba_caches_outside_the_signed_bundle(tmp_path):
    resources = fake_bundle(tmp_path)
    home = tmp_path / "home"
    got = bundle.environment(resources, {}, home)
    assert got["NUMBA_CACHE_DIR"] == str(home / "Library/Caches/Kuulas/numba")


def test_an_explicit_numba_cache_dir_is_kept(tmp_path):
    resources = fake_bundle(tmp_path)
    got = bundle.environment(resources, {"NUMBA_CACHE_DIR": "/x"}, tmp_path)
    assert got["NUMBA_CACHE_DIR"] == "/x"


def test_log_file_is_in_the_user_library_logs(tmp_path):
    assert bundle.log_file(tmp_path) == tmp_path / "Library/Logs/Kuulas/kuulas.log"


def test_finder_launch_arguments_are_dropped():
    assert bundle.clean_argv(["x", "-psn_0_12345", "open", "a.kuulas"]) == [
        "open", "a.kuulas"]


def test_the_baked_label_is_used_when_there_is_no_checkout(tmp_path):
    package = tmp_path / "kuulas"
    package.mkdir()
    (package / "build_label.txt").write_text("v26.10.19.6+abc1234\n", encoding="utf-8")
    assert build_info.baked_label(package) == "v26.10.19.6+abc1234"


def test_no_baked_label_in_a_checkout(tmp_path):
    assert build_info.baked_label(tmp_path) is None


def test_selftest_passes_headless_and_reports_each_check(capsys):
    assert cli.main(["--selftest"]) == 0
    out = capsys.readouterr().out
    for name in ("build", "libraries", "ffmpeg", "ui", "server", "meter"):
        assert f"ok   {name}" in out, out
    assert "selftest passed" in out


def test_selftest_reports_a_failure_and_fails(monkeypatch, capsys):
    def broken() -> str:
        raise RuntimeError("no ffmpeg here")

    monkeypatch.setattr(selftest, "check_ffmpeg", broken)
    assert selftest.run() == 1
    out = capsys.readouterr().out
    assert "FAIL ffmpeg" in out
    assert "no ffmpeg here" in out
    assert "selftest FAILED" in out
