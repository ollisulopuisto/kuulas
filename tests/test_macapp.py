"""Kuulas.app launcher (WP72 step 1): the pure parts, plus a macOS-only build
into a temp folder. Nothing here launches the app or opens a window."""

from __future__ import annotations

import json
import plistlib
import shlex
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kuulas import macapp, package


def make_project(tmp_path: Path, name: str = "Show.kuulas") -> Path:
    folder = tmp_path / name
    folder.mkdir()
    (folder / "manifest.json").write_text("{}", encoding="utf-8")
    return folder


# -- project validation ----------------------------------------------------------


def test_valid_project_is_kuulas_folder_with_manifest(tmp_path):
    assert macapp.project_problem(make_project(tmp_path)) is None


def test_project_problems(tmp_path):
    plain = tmp_path / "Show"
    plain.mkdir()
    (plain / "manifest.json").write_text("{}", encoding="utf-8")
    assert macapp.project_problem(plain) == "suffix"
    empty = tmp_path / "Empty.kuulas"
    empty.mkdir()
    assert macapp.project_problem(empty) == "manifest"
    (tmp_path / "File.kuulas").write_text("x", encoding="utf-8")
    assert macapp.project_problem(tmp_path / "File.kuulas") == "folder"
    assert macapp.project_problem(tmp_path / "Nope.kuulas") == "folder"


def test_project_path_with_trailing_slash_is_accepted(tmp_path):
    folder = make_project(tmp_path)
    assert macapp.project_problem(str(folder) + "/") is None


# -- quoting ---------------------------------------------------------------------


def test_launch_command_quotes_spaces_and_quotes():
    cmd = macapp.launch_command("/r e/po", "/p/It's a \"show\".kuulas", "/u/uvx")
    parts = shlex.split(cmd)
    assert parts[:2] == ["/u/uvx", "--from"]
    assert parts[2] == "/r e/po[desktop]"
    assert parts[3:5] == ["--with-editable", "/r e/po[desktop]"]
    assert parts[5:] == ["kuulas", "open", "/p/It's a \"show\".kuulas", "--window"]


def test_launch_command_cannot_inject():
    cmd = macapp.launch_command("/r", "/p/$(rm -rf ~); `x`.kuulas", "uvx")
    assert shlex.split(cmd)[-2] == "/p/$(rm -rf ~); `x`.kuulas"


def test_applescript_string_escapes():
    assert macapp.applescript_string('a"b\\c') == '"a\\"b\\\\c"'
    assert macapp.applescript_string("a\nb") == '"a" & linefeed & "b"'


# -- plist -----------------------------------------------------------------------


def test_plist_content():
    keys = macapp.plist_keys()
    assert keys["CFBundleIdentifier"] == "fi.sulopuisto.kuulas"
    doc = keys["CFBundleDocumentTypes"][0]
    assert doc["CFBundleTypeRole"] == "Editor"
    assert doc["CFBundleTypeExtensions"] == ["kuulas"]
    assert doc["LSItemContentTypes"] == ["fi.sulopuisto.kuulas.project"]
    uti = keys["UTExportedTypeDeclarations"][0]
    assert uti["UTTypeIdentifier"] == "fi.sulopuisto.kuulas.project"
    assert uti["UTTypeConformsTo"] == ["com.apple.package", "public.composite-content"]
    assert uti["UTTypeTagSpecification"]["public.filename-extension"] == ["kuulas"]
    assert keys["CFBundleIconFile"] == "kuulas"
    assert doc["CFBundleTypeIconFile"] == "kuulas-doc"
    assert uti["UTTypeIconFile"] == "kuulas-doc"
    plistlib.dumps(keys)  # serialisable


def test_bundle_id_not_used_elsewhere_in_src():
    src = Path(macapp.__file__).parent
    hits = [p for p in src.rglob("*.py")
            if "fi.sulopuisto" in p.read_text("utf-8") and p.name != "macapp.py"]
    assert hits == []


# -- applet source ---------------------------------------------------------------


def test_applet_source_has_handlers_and_commands():
    src = macapp.applet_source('/repo with "q"', "/bin/uvx", "/bin/uv", "en")
    assert "on open" in src
    assert "on run" in src
    assert '"/repo with \\"q\\""' in src
    assert "quoted form of" in src
    assert 'launchPrefix & " desktop"' in src
    assert "--window" in src
    assert "macapp.py" in src


def test_applet_source_finnish_messages():
    assert macapp.applet_source("/r", "uvx", "uv", "fi") != macapp.applet_source(
        "/r", "uvx", "uv", "en")


# -- already open ----------------------------------------------------------------


def write_lock(folder: Path, *, host: str, pid: int, age_s: float, name="a.json"):
    (folder / "locks").mkdir(exist_ok=True)
    beat = datetime.now(UTC) - timedelta(seconds=age_s)
    (folder / "locks" / name).write_text(json.dumps({
        "host": host, "pid": pid, "instance": name,
        "heartbeat_utc": beat.strftime("%Y-%m-%dT%H:%M:%SZ")}), encoding="utf-8")


def test_no_locks_means_not_open(tmp_path):
    p = make_project(tmp_path)
    assert macapp.open_here(p, "me", is_alive=lambda _p: True) is None


def test_fresh_live_local_lock_is_open(tmp_path):
    p = make_project(tmp_path)
    write_lock(p, host="me", pid=4242, age_s=10)
    assert macapp.open_here(p, "me", is_alive=lambda _p: True) == 4242


def test_other_host_stale_or_dead_locks_do_not_count(tmp_path):
    p = make_project(tmp_path)
    write_lock(p, host="other", pid=1, age_s=10, name="b.json")
    write_lock(p, host="me", pid=2, age_s=package.STALE_S + 5, name="c.json")
    write_lock(p, host="me", pid=3, age_s=5, name="d.json")
    assert macapp.open_here(p, "me", is_alive=lambda pid: pid != 3) is None


def test_conflicted_and_broken_locks_ignored(tmp_path):
    p = make_project(tmp_path)
    write_lock(p, host="me", pid=9, age_s=1, name="x (conflicted copy).json")
    (p / "locks" / "bad.json").write_text("{", encoding="utf-8")
    assert macapp.open_here(p, "me", is_alive=lambda _p: True) is None


def test_constants_follow_package():
    assert macapp.STALE_S == package.STALE_S
    assert macapp.LOCKS_DIR == package.LOCKS_DIR


def test_check_cli_outputs(tmp_path, capsys):
    p = make_project(tmp_path)
    assert macapp.main(["check", str(p)]) == 0
    assert capsys.readouterr().out.strip() == "ok"
    assert macapp.main(["check", str(tmp_path / "x")]) == 0
    assert capsys.readouterr().out.strip() == "invalid"


# -- plan and build --------------------------------------------------------------


def test_plan_lists_steps(tmp_path):
    tools = {"uvx": "/bin/uvx", "uv": "/bin/uv"}
    text = "\n".join(macapp.plan(tmp_path / "out", "/repo", register=False, tools=tools))
    assert "osacompile" in text
    assert "Kuulas.app" in text
    assert "lsregister" not in text
    with_reg = "\n".join(macapp.plan(tmp_path / "out", "/repo", register=True,
                                     tools=tools))
    assert "lsregister -f" in with_reg
    assert "lsregister -u" in with_reg


def test_dry_run_builds_nothing(tmp_path, capsys):
    out = tmp_path / "out"
    code = macapp.build_main(["--dry-run", "--into", str(out), "--no-register"])
    assert code == 0
    assert not out.exists()
    assert "osacompile" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("osacompile"),
                    reason="osacompile exists only on macOS")
def test_build_on_macos(tmp_path):
    out = tmp_path / "Apps"
    code = macapp.build_main(["--into", str(out), "--no-register"])
    assert code == 0
    app = out / "Kuulas.app"
    assert any((app / "Contents" / "MacOS").iterdir())  # "droplet": it has `on open`
    assert not list((app / "Contents" / "Resources").glob("droplet.icns"))
    info = app / "Contents" / "Info.plist"
    subprocess.run(["plutil", "-lint", str(info)], check=True,  # noqa: S603, S607
                   capture_output=True)
    data = plistlib.loads(info.read_bytes())
    assert data["CFBundleIdentifier"] == "fi.sulopuisto.kuulas"
    assert data["UTExportedTypeDeclarations"][0]["UTTypeConformsTo"][0] == (
        "com.apple.package")
    assert (app / "Contents" / "Resources" / "kuulas.icns").exists()
    assert (app / "Contents" / "Resources" / "kuulas-doc.icns").exists()
    # rebuilding replaces
    assert macapp.build_main(["--into", str(out), "--no-register"]) == 0
