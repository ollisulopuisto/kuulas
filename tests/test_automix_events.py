"""Live events from the automixer (``--events``): ``@@kuulas {json}`` lines on stdout.

A fake automixer prints events and text. Kuulas parses the events, never shows them as
text, and falls back to the text lines when none arrive."""

import json
import sys
import textwrap
import threading
from pathlib import Path

import pytest
from test_automix import Reports, voice
from test_automix_remote import FAKE_RSYNC, FAKE_SSH

from kuulas import automix
from kuulas.session import Session

EV = "@@kuulas "

SCRIPT = textwrap.dedent('''
    import json, os, sys
    import numpy as np, soundfile as sf
    argv = sys.argv[1:]
    if "--help" in argv:
        print("usage: fake")
        if os.environ.get("FAKE_HAS_EVENTS", "1") == "1":
            print("  --events   print @@kuulas lines")
        sys.exit(0)
    out = argv[argv.index("-o") + 1]
    with open(os.environ["FAKE_LOG"], "w") as f:
        json.dump({"argv": argv}, f)
    open(os.path.splitext(out)[0] + " flags.txt", "w").close()
    def ev(**kw):
        print("@@kuulas " + json.dumps({"schema": 1, **kw}), flush=True)
    if "--events" in argv:
        print("@@kuulas {not json", flush=True)
        print("@@kuulas [1, 2]", flush=True)
        print("@@kuulas " + json.dumps({"schema": 1}), flush=True)
        ev(event="future_thing", x=1)
        ev(event="track", index=1, total=2, name="Olli")
        ev(event="stage", track="Olli", stage="read", state="start")
        ev(event="stage", track="Olli", stage="read", state="done")
        ev(event="stage", track="Olli", stage="plugin", state="start")
        ev(event="progress", percent=40, message="Olli: read")
        ev(event="progress", percent=20, message="late")
        ev(event="warning", message="plug-in missing")
        ev(event="bed", loudest_lufs=-10.5, speech_lufs=-20.7, offset_db=-10.0)
        ev(event="balance", track="Olli", lufs=-19.0, applied_db=1.5, limit_db=6.0)
        ev(event="mastered", lufs=-16.0, lift_db=2.0, limiting_lu=1.0)
        ev(event="done", path=out)
    print("PROGRESS 40 Olli: read", flush=True)
    print("beds: loudest -10.5 LUFS, speech -20.7 -> beds -10.0 dB", flush=True)
    sf.write(out, np.zeros(4800, dtype="float32"), 48000)
    print("PROGRESS 100 done", flush=True)
''')


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    src = tmp_path / "src"
    src.mkdir()
    s.import_media([str(voice(src / "Olli.wav", 3, 1)),
                    str(voice(src / "Maija.wav", 3, 2))])
    yield s
    s.close()


@pytest.fixture
def tool(tmp_path, monkeypatch):
    script = tmp_path / "fake_events.py"
    script.write_text(SCRIPT, encoding="utf-8")
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "call.json"))
    automix.clear_capability_cache()
    yield {"command": [sys.executable, str(script)], "cwd": str(tmp_path),
           "extra_args": []}
    automix.clear_capability_cache()


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setattr(automix.tempfile, "tempdir", str(root))
    return root


def mix(session, settings):
    reports, live = Reports(), []
    result = automix.run(session, {}, settings, reports, threading.Event(),
                         live=live.append)
    return result, reports, live


def argv(tmp_path):
    return json.loads((tmp_path / "call.json").read_text())["argv"]


# -- parse_event ------------------------------------------------------------------------

def test_parse_event_returns_the_object():
    got = automix.parse_event(EV + '{"schema": 1, "event": "bed", "offset_db": -3}')
    assert got == {"schema": 1, "event": "bed", "offset_db": -3}


@pytest.mark.parametrize("line", [
    "", "plain text", "PROGRESS 5 x", "@@kuulas", "@@kuulas ", "@@kuulas {broken",
    "@@kuulas [1]", "@@kuulas 5", '@@kuulas "s"', "@@kuulas null", "@@kuulas {}",
    '@@kuulas {"schema": 1}', '@@kuulas {"event": 7}', '@@kuulas {"event": ""}',
    '  @@kuulas {"event": "x"}',
])
def test_parse_event_is_none_for_anything_else(line):
    assert automix.parse_event(line) is None


def test_parse_event_tolerates_a_future_schema_and_odd_schema_values():
    assert automix.parse_event(EV + '{"schema": 7, "event": "x", "new": [1]}')
    assert automix.parse_event(EV + '{"schema": "one", "event": "x"}')
    assert automix.parse_event(EV + '{"event": "x"}') == {"event": "x"}


def test_is_event_line_even_when_unparseable():
    assert automix.is_event_line("@@kuulas {broken")
    assert not automix.is_event_line("hello")


# -- the flag ---------------------------------------------------------------------------

def test_events_flag_is_sent_when_help_lists_it(session, tool, temp_root, tmp_path):
    automix.run(session, {}, tool, Reports(), threading.Event())
    assert "--events" in argv(tmp_path)


def test_events_flag_is_not_sent_when_help_does_not_list_it(
        session, tool, temp_root, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_HAS_EVENTS", "0")
    automix.run(session, {}, tool, Reports(), threading.Event())
    assert "--events" not in argv(tmp_path)


def test_capabilities_keeps_its_shape_and_events_has_its_own_answer():
    def helper(cmd, _cwd, on_line, _cancel):
        on_line("--events --bed-under-speech-db")
        return 0
    automix.clear_capability_cache()
    assert automix.capabilities(["a"], None, run_process=helper) == {
        "bed_under_speech_db": True, "balance_speakers_max_db": False}
    assert automix.supports_events(["a"], None, run_process=helper) is True
    automix.clear_capability_cache()


def test_build_command_appends_events_only_when_told():
    settings = {"command": ["a"], "extra_args": ["-x"]}
    plain = automix.build_command(settings, Path("/s"), Path("/o.wav"),
                                  target_lufs=-16, ad_spot=None, ad_duration=None)
    with_events = automix.build_command(
        settings, Path("/s"), Path("/o.wav"), target_lufs=-16, ad_spot=None,
        ad_duration=None, events=True)
    assert "--events" not in plain
    assert with_events == [*plain[:-1], "--events", "-x"]


# -- the run ----------------------------------------------------------------------------

def test_event_lines_are_never_shown_as_text(session, tool, temp_root):
    result, reports, live = mix(session, tool)
    assert not [x for x in live if "@@kuulas" in x]
    assert not [m for _f, m, _i in reports.items if "@@kuulas" in m]
    assert not [x for x in result["log"] if "@@kuulas" in x]
    assert "@@kuulas" not in Path(result["log_file"]).read_text()


def test_the_bar_never_goes_back_with_both_sources(session, tool, temp_root):
    _result, reports, _live = mix(session, tool)
    fractions = [f for f, _m, _i in reports.items]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0


def test_a_stage_start_says_it_is_working_now(session, tool, temp_root):
    _result, reports, _live = mix(session, tool)
    messages = [m for _f, m, _i in reports.items]
    assert any("Olli: plugin" in m and "now" not in m for m in messages)


def test_a_warning_event_is_a_warning_line(session, tool, temp_root):
    result, _reports, live = mix(session, tool)
    assert any(x.startswith("kuulas: ") and "plug-in missing" in x for x in live)
    assert any("plug-in missing" in w for w in result["warnings"])


def test_the_last_bed_balance_and_mastered_events_are_kept(session, tool, temp_root):
    result, _reports, _live = mix(session, tool)
    events = result["events"]
    assert events["bed"]["offset_db"] == -10.0
    assert events["balance"]["Olli"]["applied_db"] == 1.5
    assert events["mastered"]["lufs"] == -16.0
    assert "future_thing" not in events


def test_the_log_gets_a_compact_line_per_event(session, tool, temp_root):
    result, _reports, _live = mix(session, tool)
    text = Path(result["log_file"]).read_text()
    assert "bed: loudest -10.5 LUFS, speech -20.7, offset -10.0 dB" in text


def test_without_events_the_run_is_as_before(session, tool, temp_root, monkeypatch):
    monkeypatch.setenv("FAKE_HAS_EVENTS", "0")
    result, reports, live = mix(session, tool)
    assert result["events"] == {}
    assert live[-1] == "PROGRESS 100 done"
    assert reports.items[-1][0] == 1.0


def test_a_stage_event_without_fields_never_raises():
    steps = automix.StepTracker(["Olli"])
    assert steps.event({"event": "stage"}) is None
    assert steps.event({"event": "stage", "track": None, "stage": 5,
                        "state": []}) is None
    assert steps.event({"event": "track", "index": "x"}) is None
    assert "plugin" in steps.event({"event": "stage", "track": "Olli",
                                    "stage": "plugin", "state": "start"})


# -- over ssh ---------------------------------------------------------------------------

def test_remote_events_come_through_the_same_path(session, tool, temp_root, tmp_path):
    ssh = tmp_path / "fake_ssh.py"
    ssh.write_text(FAKE_SSH, encoding="utf-8")
    rsync = tmp_path / "fake_rsync.py"
    rsync.write_text(FAKE_RSYNC, encoding="utf-8")
    cwd = tmp_path / "remote cwd"
    cwd.mkdir()
    settings = {"remote": {
        "enabled": True, "host": "studio", "cwd": str(cwd),
        "work_dir": str(tmp_path / "work"), "command": tool["command"],
        "ssh_command": [sys.executable, str(ssh)],
        "rsync_command": [sys.executable, str(rsync)]}}
    result, reports, live = mix(session, settings)
    assert "--events" in argv(tmp_path)
    assert not [x for x in live if "@@kuulas" in x]
    assert result["events"]["bed"]["offset_db"] == -10.0
    fractions = [f for f, _m, _i in reports.items]
    assert fractions == sorted(fractions)
