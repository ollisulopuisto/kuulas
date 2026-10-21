"""The automixer shipped inside Kuulas.app: which command runs when nothing is set, how
the bundle starts it, its ``--help`` probe, and the messages when it cannot start.

Only fake automixers: a fake installed distribution (an ``automixer`` console script
pointing at a tiny module) and fake runners. The real automixer never runs here."""

from __future__ import annotations

import sys
import textwrap
import threading
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import automix, bundle, messages, plugins, selftest
from kuulas.session import Session

BUNDLED = [sys.executable, "-m", "automixer"]

FAKE_MODULE = textwrap.dedent('''
    import sys

    def main():
        if "--help" in sys.argv[1:]:
            print("usage: automixer [-h] [--speech-plugins P [P ...]] [--events]")
            print("  --keep-music-level   keep the beds where the stems have them")
            raise SystemExit(0)
        print("fake automixer ran with", sys.argv[1:])
        return 0
''')


def fake_installed_automixer(root: Path, module: str = FAKE_MODULE) -> Path:
    """A folder holding an installed ``automixer`` distribution as pip lays one out: the
    console script ``automixer`` in ``entry_points.txt`` (no ``__main__.py``, as in the
    podcast repo today), pointing at ``fake_automixer_cli:main``."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "fake_automixer_cli.py").write_text(module, encoding="utf-8")
    info = root / "automixer-1.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: automixer\nVersion: 1\n",
                                   encoding="utf-8")
    (info / "entry_points.txt").write_text(
        "[console_scripts]\nautomixer = fake_automixer_cli:main\n", encoding="utf-8")
    return root


# --- which command runs -------------------------------------------------------------


def test_the_bundled_automixer_runs_when_no_command_is_set(tmp_path, monkeypatch):
    monkeypatch.setattr(automix, "bundled_command", lambda: list(BUNDLED))
    # Even with the owner's checkout on this Mac: the app's own automixer, no folder.
    (tmp_path / "Documents" / "koodi" / "podcast").mkdir(parents=True)
    s = automix.resolve_settings({}, home=tmp_path)
    assert s["command"] == BUNDLED
    assert s["cwd"] is None


def test_a_command_set_in_the_settings_wins_over_the_bundled_one(tmp_path, monkeypatch):
    monkeypatch.setattr(automix, "bundled_command", lambda: list(BUNDLED))
    (tmp_path / "Documents" / "koodi" / "podcast").mkdir(parents=True)
    s = automix.resolve_settings({"command": ["uv", "run", "automixer"]}, home=tmp_path)
    assert s["command"] == ["uv", "run", "automixer"]
    assert s["cwd"] == str(tmp_path / "Documents" / "koodi" / "podcast")
    s = automix.resolve_settings({"cwd": "/somewhere"}, home=tmp_path)
    assert s["command"] == BUNDLED
    assert s["cwd"] == "/somewhere"


def test_from_source_without_a_bundle_it_is_uv_run_in_the_checkout(tmp_path):
    # This test process runs from the checkout: no bundle, so no bundled command.
    assert automix.bundled_command() is None
    (tmp_path / "Documents" / "koodi" / "podcast").mkdir(parents=True)
    s = automix.resolve_settings({}, home=tmp_path)
    assert s["command"] == ["uv", "run", "automixer"]
    assert s["cwd"] == str(tmp_path / "Documents" / "koodi" / "podcast")


def test_bundled_command_needs_both_the_bundle_and_the_package(tmp_path):
    resources = tmp_path / "Kuulas.app" / "Contents" / "Resources"
    module = resources / "app" / "kuulas" / "automix.py"
    module.parent.mkdir(parents=True)
    found = automix.bundled_command(module_file=module, find_spec=lambda _n: object())
    assert found == [sys.executable, "-m", "automixer"]
    assert automix.bundled_command(module_file=module, find_spec=lambda _n: None) is None
    assert automix.bundled_command(module_file=tmp_path / "kuulas" / "automix.py",
                                   find_spec=lambda _n: object()) is None


# --- the bundle starts it -----------------------------------------------------------


def test_the_bundle_hands_minus_m_automixer_on():
    assert bundle.automixer_args(["-m", "automixer", "--help"]) == ["--help"]
    assert bundle.automixer_args(["-m", "automixer"]) == []
    assert bundle.automixer_args(["-m", "kuulas_recorder"]) is None
    assert bundle.automixer_args(["open", "a.kuulas"]) is None


def test_bundle_main_runs_the_automixer_without_opening_the_log(monkeypatch):
    ran = []
    monkeypatch.setattr(bundle, "_run_automixer", lambda args: ran.append(args) or 0)
    monkeypatch.setattr(bundle, "_open_log", lambda *_a: ran.append("log"))
    monkeypatch.setattr("sys.argv", ["Kuulas", "-m", "automixer", "--help"])
    assert bundle.main() == 0
    assert ran == [["--help"]]  # its stdout is what Kuulas reads: never the log


def test_the_console_script_runs_in_process(tmp_path, monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(fake_installed_automixer(tmp_path / "site")))
    monkeypatch.setattr("sys.argv", ["Kuulas"])
    assert bundle._run_automixer(["--help"]) == 0
    assert "--keep-music-level" in capsys.readouterr().out


def test_a_missing_automixer_is_an_import_error_line(capsys):
    assert bundle._run_automixer(["--help"]) == 1
    err = capsys.readouterr().err
    assert "ModuleNotFoundError: No module named 'automixer'" in err


def test_the_help_probe_works_through_the_bundle_entry(tmp_path, monkeypatch):
    # As the app runs it: the launcher is ``python -m kuulas`` with ``-m automixer ...``.
    site = fake_installed_automixer(tmp_path / "site")
    src = Path(automix.__file__).resolve().parent.parent
    monkeypatch.setenv("PYTHONPATH", f"{site}:{src}")
    automix.clear_capability_cache()
    command = [sys.executable, "-m", "kuulas", "-m", "automixer"]
    assert automix.supports_keep_music_level(command, None, timeout=60) is True
    assert automix.supports_events(command, None, timeout=60) is True


# --- when it cannot start -----------------------------------------------------------

RATE = 48000


class Reports:
    def __call__(self, fraction, message="", *, indeterminate=False):
        pass


@pytest.fixture
def session(tmp_path):
    rng = np.random.default_rng(1)
    src = tmp_path / "src"
    src.mkdir()
    sf.write(src / "Olli.wav", (rng.standard_normal(RATE * 2) * 0.1).astype(np.float32),
             RATE, subtype="PCM_16")
    s = Session(tmp_path / "Episode.kuulas")
    s.import_media([str(src / "Olli.wav")])
    yield s
    s.close()


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setattr(automix.tempfile, "tempdir", str(root))
    return root


@pytest.fixture
def fake(tmp_path):
    """Settings for a local run; every test here gives its own runner."""
    return {"command": [sys.executable, "-c", "pass"], "cwd": str(tmp_path),
            "extra_args": []}


def in_both(key: str, params: dict) -> list[str]:
    """The message in English and in Finnish."""
    out = []
    try:
        for lang in ("en", "fi"):
            messages.set_language(lang)
            out.append(str(messages.t(key, **params)))
    finally:
        messages.set_language("en")
    return out


def traceback_runner(last: str):
    def runner(_cmd, _cwd, on_line, _cancel):
        for line in ("Traceback (most recent call last):",
                     '  File "automixer/cli_mix.py", line 18, in <module>',
                     "    import pyloudnorm", last):
            on_line(line)
        return 1
    return runner


@pytest.mark.parametrize("last", [
    "ModuleNotFoundError: No module named 'pyloudnorm'",
    "ImportError: dlopen(_pedalboard.so, 0x0002): Library not loaded: libfoo.dylib"])
def test_an_import_error_is_a_specific_message_not_a_traceback(
        session, fake, temp_root, last):
    with pytest.raises(automix.AutomixError) as e:
        automix.run(session, {}, fake, Reports(), threading.Event(),
                    run_process=traceback_runner(last))
    assert e.value.key == "error.automix.cannot_start"
    detail = last.split(": ", 1)[1]
    for text in in_both(e.value.key, e.value.params):
        assert detail in text
        assert "Traceback" not in text
    assert e.value.params["log_file"]  # the whole output is kept beside the mix


def test_an_ordinary_failure_stays_the_ordinary_message(session, fake, temp_root):
    with pytest.raises(automix.AutomixError) as e:
        automix.run(session, {}, fake, Reports(), threading.Event(),
                    run_process=traceback_runner("ValueError: bad stems"))
    assert e.value.key == "error.automix.failed"


def test_a_missing_plugin_is_named_with_where_it_was_looked_for(
        session, fake, temp_root, monkeypatch):
    ran = []
    monkeypatch.setattr(plugins, "list_plugins", lambda refresh=False: [])
    fake["options"] = {"speech_plugins": ["dxRevive"]}
    with pytest.raises(automix.AutomixError) as e:
        automix.run(session, {}, fake, Reports(), threading.Event(),
                    run_process=lambda *a: ran.append(a) or 0)
    assert e.value.key == "error.automix.plugin_missing"
    assert ran == []  # nothing exported, nothing run
    assert list(temp_root.iterdir()) == []
    for text in in_both(e.value.key, e.value.params):
        assert "dxRevive" in text
        assert "/Library/Audio/Plug-Ins/VST3" in text


def test_a_plugin_path_that_is_gone_is_named_too(session, fake, temp_root, tmp_path):
    gone = str(tmp_path / "Gone.vst3")
    fake["options"] = {"music_plugins": [gone]}
    with pytest.raises(automix.AutomixError) as e:
        automix.run(session, {}, fake, Reports(), threading.Event(),
                    run_process=lambda *a: 0)
    assert e.value.key == "error.automix.plugin_missing"
    assert gone in str(messages.t(e.value.key, **e.value.params))


def test_a_name_that_matches_no_installed_plugin_is_plugin_missing(monkeypatch):
    monkeypatch.setattr(plugins, "list_plugins", lambda refresh=False: [
        {"name": "Other", "path": "/Library/Audio/Plug-Ins/VST3/Other.vst3",
         "format": "VST3"}])
    with pytest.raises(automix.AutomixError) as e:
        automix.normalize_options({"speech_plugins": ["zzzqqq"]})
    assert e.value.key == "error.automix.plugin_missing"


# --- the in-app selftest ------------------------------------------------------------


def test_selftest_runs_the_automixer_help(monkeypatch, tmp_path):
    site = fake_installed_automixer(tmp_path / "site")
    src = Path(automix.__file__).resolve().parent.parent
    monkeypatch.setenv("PYTHONPATH", f"{site}:{src}")
    monkeypatch.setattr(selftest, "_in_bundle", lambda: True)
    monkeypatch.setattr(automix, "bundled_command",
                        lambda: [sys.executable, "-m", "kuulas", "-m", "automixer"])
    detail = selftest.check_automixer()
    assert "--help" in detail
    assert "keep-music-level" in detail


def test_selftest_fails_when_the_bundle_has_no_automixer(monkeypatch):
    monkeypatch.setattr(selftest, "_in_bundle", lambda: True)
    monkeypatch.setattr(automix, "bundled_command", lambda: None)
    with pytest.raises(selftest.SelftestError, match="automixer"):
        selftest.check_automixer()


def test_selftest_fails_when_the_automixer_cannot_start(monkeypatch, tmp_path):
    site = fake_installed_automixer(tmp_path / "site", "import no_such_module_xyz\n")
    src = Path(automix.__file__).resolve().parent.parent
    monkeypatch.setenv("PYTHONPATH", f"{site}:{src}")
    monkeypatch.setattr(selftest, "_in_bundle", lambda: True)
    monkeypatch.setattr(automix, "bundled_command",
                        lambda: [sys.executable, "-m", "kuulas", "-m", "automixer"])
    with pytest.raises(selftest.SelftestError, match="no_such_module_xyz"):
        selftest.check_automixer()


def test_selftest_from_source_only_reports_the_automixer():
    assert "automixer" in selftest.CHECKS
    assert "not bundled" in selftest.check_automixer()
