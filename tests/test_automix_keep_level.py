"""Music level: "keep my levels" (--keep-music-level) against "fit to speech"
(--bed-under-speech-db). The flag is probed from --help; the two exclude each other;
keep is the default when the automixer has it; the bed event says which mode ran."""

import json
import sys
import textwrap
import threading
from pathlib import Path

import pytest
from test_automix import Reports, voice

from kuulas import automix, series_settings
from kuulas.session import Session

SCRIPT = textwrap.dedent('''
    import json, os, sys
    import numpy as np, soundfile as sf
    argv = sys.argv[1:]
    if "--help" in argv:
        print("usage: fake")
        if os.environ.get("FAKE_KEEP", "1") == "1":
            print("  --keep-music-level   music gets the speech's change")
        print("  --bed-under-speech-db FLOAT  fit")
        print("  --events   print @@kuulas lines")
        sys.exit(0)
    out = argv[argv.index("-o") + 1]
    with open(os.environ["FAKE_LOG"], "w") as f:
        json.dump({"argv": argv}, f)
    open(os.path.splitext(out)[0] + " flags.txt", "w").close()
    if "--events" in argv:
        bed = {"schema": 1, "event": "bed", "loudest_lufs": -30.0, "speech_lufs": -20.0,
               "offset_db": 0.0}
        if "--keep-music-level" in argv:
            bed.update(mode="keep", change_db=3.5, offset_db=0.0, speech_lufs=-18.5,
                       speech_raw_lufs=-22.0)
        elif os.environ.get("FAKE_MODE_FIT") == "1":
            bed.update(mode="fit")
        print("@@kuulas " + json.dumps(bed), flush=True)
    sf.write(out, np.zeros(4800, dtype="float32"), 48000)
    print("PROGRESS 100 done", flush=True)
''')


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    src = tmp_path / "src"
    src.mkdir()
    s.import_media([str(voice(src / "Olli.wav", 3, 1))])
    yield s
    s.close()


@pytest.fixture
def tool(tmp_path, monkeypatch):
    script = tmp_path / "fake_keep.py"
    script.write_text(SCRIPT, encoding="utf-8")
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "call.json"))
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setattr(automix.tempfile, "tempdir", str(root))
    automix.clear_capability_cache()
    yield {"command": [sys.executable, str(script)], "cwd": str(tmp_path),
           "extra_args": []}
    automix.clear_capability_cache()


def mix(session, tool, options=None):
    live = []
    settings = {**tool, "options": options or {}}
    result = automix.run(session, {}, settings, Reports(), threading.Event(),
                         live=live.append)
    return result, live


def argv(tmp_path):
    return json.loads((tmp_path / "call.json").read_text())["argv"]


def test_spec_is_an_unset_by_default_music_switch():
    spec = automix.OPTIONS["keep_music_level"]
    assert (spec["flag"], spec["kind"], spec["default"], spec["group"]) == (
        "--keep-music-level", "bool", None, "music")


def test_both_choices_are_stored_and_unset_is_not():
    assert automix.normalize_options({"keep_music_level": True}) == {
        "keep_music_level": True}
    assert automix.normalize_options({"keep_music_level": False}) == {
        "keep_music_level": False}
    assert automix.normalize_options({"keep_music_level": None}) == {}
    with pytest.raises(automix.AutomixError):
        automix.normalize_options({"keep_music_level": "yes"})


def test_probe_reads_the_flag_from_help():
    def helper(text):
        def run(cmd, _cwd, on_line, _cancel):
            on_line(text)
            return 0
        return run
    automix.clear_capability_cache()
    assert automix.supports_keep_music_level(["a"], None, run_process=helper(
        "--keep-music-level  x")) is True
    automix.clear_capability_cache()
    assert automix.supports_keep_music_level(["a"], None, run_process=helper(
        "--bed-under-speech-db")) is False
    automix.clear_capability_cache()


def test_the_flag_is_sent_when_kept_and_never_with_the_bed_level(tool, session, tmp_path):
    mix(session, tool, {"bed_under_speech_db": -8.0, "keep_music_level": True})
    args = argv(tmp_path)
    assert "--keep-music-level" in args
    assert "--bed-under-speech-db" not in args


def test_keep_is_the_default_when_the_automixer_has_it(tool, session, tmp_path):
    mix(session, tool)
    assert "--keep-music-level" in argv(tmp_path)


def test_an_unset_choice_with_a_bed_level_means_fit(tool, session, tmp_path):
    mix(session, tool, {"bed_under_speech_db": -8.0})
    args = argv(tmp_path)
    assert "--keep-music-level" not in args
    assert args[args.index("--bed-under-speech-db") + 1] == "-8"


def test_keep_beside_a_bed_level_drops_the_bed_and_logs_it(tool, session):
    result, _live = mix(session, tool, {"bed_under_speech_db": -8.0,
                                        "keep_music_level": True})
    assert "not applied" in Path(result["log_file"]).read_text()


@pytest.mark.parametrize("supported", [None, {"bed_under_speech_db": True}])
def test_the_builder_never_emits_both_flags(supported):
    settings = {"command": ["a"], "extra_args": [],
                "options": {"keep_music_level": True, "bed_under_speech_db": -8.0}}
    cmd = automix.build_command(settings, Path("/s"), Path("/o.wav"), target_lufs=-16,
                                ad_spot=None, ad_duration=None, supported=supported)
    assert "--bed-under-speech-db" not in cmd
    assert cmd.count("--keep-music-level") == 1


def test_apply_never_writes_both(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(tmp_path / "automixer.json"))
    automix.merge_options({"keep_music_level": True, "bed_under_speech_db": -8.0})
    options = automix.load_settings()["options"]
    assert options["keep_music_level"] is True
    assert "bed_under_speech_db" not in options


def test_fit_sends_the_bed_level_and_not_the_keep_flag(tool, session, tmp_path):
    mix(session, tool, {"bed_under_speech_db": -8.0, "keep_music_level": False})
    args = argv(tmp_path)
    assert "--keep-music-level" not in args
    assert args[args.index("--bed-under-speech-db") + 1] == "-8"


def test_an_old_automixer_runs_as_before(tool, session, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_KEEP", "0")
    result, _live = mix(session, tool, {"bed_under_speech_db": -8.0})
    args = argv(tmp_path)
    assert "--keep-music-level" not in args
    assert args[args.index("--bed-under-speech-db") + 1] == "-8"
    assert result["warnings"] == []  # the default is not a request: nothing to warn about


def test_asking_for_keep_on_an_old_automixer_warns(tool, session, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_KEEP", "0")
    result, _live = mix(session, tool, {"keep_music_level": True})
    assert "--keep-music-level" not in argv(tmp_path)
    assert len(result["warnings"]) == 1


def test_the_keep_bed_event_is_logged_and_shown_live(tool, session):
    result, live = mix(session, tool)
    shifted = "Music: kept your level, +3.5 dB like the speech"
    assert any(shifted in x for x in live)
    assert shifted in Path(result["log_file"]).read_text()
    assert result["events"]["bed"]["mode"] == "keep"


def test_the_shift_falls_back_to_the_two_speech_levels():
    line = automix.event_log_line({"event": "bed", "mode": "keep", "speech_lufs": -18.5,
                                   "speech_raw_lufs": -22.0})
    assert "+3.5 dB" in line


def test_a_keep_event_with_nothing_measured_never_raises():
    assert "?" in automix.event_log_line({"event": "bed", "mode": "keep"})


def test_a_fit_or_old_bed_event_reads_as_before():
    old = {"event": "bed", "loudest_lufs": -10.5, "speech_lufs": -20.7,
           "offset_db": -10.0}
    want = "bed: loudest -10.5 LUFS, speech -20.7, offset -10.0 dB"
    assert automix.event_log_line(old) == want
    assert automix.event_log_line({**old, "mode": "fit"}) == want


def test_series_settings_carry_the_mode_and_apply_writes_it(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(tmp_path / "automixer.json"))
    assert "keep_music_level" in series_settings.AUTOMIX_KEYS
    assert series_settings.automix_values({})["keep_music_level"] is None
    assert series_settings.automix_values({"keep_music_level": False})[
        "keep_music_level"] is False
    automix.merge_options({"keep_music_level": False})
    assert automix.load_settings()["options"]["keep_music_level"] is False
    automix.merge_options({"keep_music_level": None})
    assert "keep_music_level" not in automix.load_settings()["options"]
