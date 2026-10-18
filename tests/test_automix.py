"""Mix with the automixer (WP68 step 1): the runner, with a fake automixer.

The fake is a tiny Python script that takes the automixer's command line, writes
a wav to ``-o`` and prints progress. No real automixer, no audio playback."""

import json
import sys
import textwrap
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import automix, messages
from kuulas.jobs import JobCancelledError
from kuulas.session import Session

RATE = 48000

FAKE = textwrap.dedent('''
    import json, os, sys, time
    import numpy as np, soundfile as sf
    argv = sys.argv[1:]
    mode = argv[argv.index("--mode") + 1] if "--mode" in argv else "ok"
    out = argv[argv.index("-o") + 1]
    valued = {"-o", "--mode", "--target-lufs", "--ad-spot", "--ad-duration"}
    files, i = [], 0
    while i < len(argv):
        if argv[i] in valued:
            i += 2
        elif argv[i].startswith("--"):
            i += 1
        else:
            files.append(argv[i])
            i += 1
    with open(os.environ["FAKE_LOG"], "w") as f:
        json.dump({"argv": argv, "files": files, "cwd": os.getcwd(),
                   "exists": [os.path.exists(p) for p in files]}, f)
    print("loading", len(files), "tracks", flush=True)
    if mode == "fail":
        print("boom: no plug-in", flush=True)
        sys.exit(3)
    if mode == "hang":
        sf.write(out, np.zeros(100, dtype="float32"), 48000)
        print("working", flush=True)
        time.sleep(60)
    for pct in (25, 50, 75):
        print(f"mixing {pct}%", flush=True)
    sf.write(out, np.zeros(4800, dtype="float32"), 48000)
    print("done", flush=True)
''')


def voice(path: Path, seconds: float, seed: int) -> Path:
    rng = np.random.default_rng(seed)
    audio = (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32)
    sf.write(path, audio, RATE, subtype="PCM_16")
    return path


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
def fake(tmp_path, monkeypatch):
    script = tmp_path / "fake_automixer.py"
    script.write_text(FAKE, encoding="utf-8")
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "call.json"))
    return {"command": [sys.executable, str(script)], "cwd": str(tmp_path),
            "extra_args": []}


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    """Where the runner makes its temporary stems folder, to look at afterwards."""
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setattr(automix.tempfile, "tempdir", str(root))
    return root


def call(tmp_path) -> dict:
    return json.loads((tmp_path / "call.json").read_text())


class Reports:
    def __init__(self):
        self.items = []

    def __call__(self, fraction, message="", *, indeterminate=False):
        self.items.append((fraction, message, indeterminate))


def test_defaults_when_nothing_is_stored(tmp_path):
    s = automix.resolve_settings({}, home=tmp_path)
    assert s["command"] == ["uv", "run", "automixer"]
    assert s["extra_args"] == []
    assert s["cwd"] is None  # no ~/Documents/koodi/podcast here
    (tmp_path / "Documents" / "koodi" / "podcast").mkdir(parents=True)
    s = automix.resolve_settings({}, home=tmp_path)
    assert s["cwd"] == str(tmp_path / "Documents" / "koodi" / "podcast")
    given = {"cwd": "/x", "extra_args": ["--minimal"]}
    s = automix.resolve_settings(given, home=tmp_path)
    assert s["cwd"] == "/x"
    assert s["extra_args"] == ["--minimal"]


def test_command_line_is_an_argument_list():
    settings = {"command": ["uv", "run", "automixer"],
                "extra_args": ["--speech-plugins", "dxRevive"]}
    cmd = automix.build_command(
        settings, [Path("/s/a.wav"), Path("/s/b MUSIC.wav")], Path("/o/out.wav"),
        target_lufs=-16, ad_spot=None, ad_duration=None)
    assert cmd == ["uv", "run", "automixer", "/s/a.wav", "/s/b MUSIC.wav",
                   "-o", "/o/out.wav", "--target-lufs", "-16",
                   "--speech-plugins", "dxRevive"]
    cmd = automix.build_command(
        {"command": ["automixer"], "extra_args": []}, [Path("/s/a.wav")],
        Path("/o/x.wav"), target_lufs=-14.5, ad_spot=1200, ad_duration=45)
    assert cmd[-4:] == ["--ad-spot", "1200", "--ad-duration", "45"]
    assert "-14.5" in cmd


@pytest.mark.parametrize("params", [{"target_lufs": "loud"}, {"target_lufs": -90},
                                    {"ad_spot": -1}, {"ad_duration": 0}])
def test_bad_parameters_are_refused(session, fake, params):
    with pytest.raises(automix.AutomixError) as e:
        automix.run(session, params, fake, Reports(), threading.Event())
    assert e.value.key.startswith("error.automix.bad_")


def test_success_runs_the_command_on_the_stems_and_cleans_up(
        session, fake, tmp_path, temp_root):
    reports = Reports()
    result = automix.run(
        session, {"target_lufs": -14, "ad_spot": 30}, fake, reports, threading.Event())
    out = Path(result["path"])
    assert out.exists()
    assert out.suffix == ".wav"
    assert out.parent == tmp_path / "Episode exports"
    assert " automixer " in out.name
    assert not list(out.parent.glob("*.partial*"))
    seen = call(tmp_path)
    assert seen["cwd"] == str(tmp_path)
    assert len(seen["files"]) == 2
    assert all(seen["exists"])  # stems existed during the run
    assert "-14" in seen["argv"]
    assert "--ad-spot" in seen["argv"]
    assert list(temp_root.iterdir()) == []  # temporary stems are gone
    fractions = [r[0] for r in reports.items]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0
    assert any(f <= 0.4 for f in fractions)
    assert any(m == "mixing 50%" for _f, m, _i in reports.items)
    # the real CLI prints no percentage, so after the stems the bar is indeterminate
    # and any "42%" in a log line is only text
    log_reports = [r for r in reports.items if r[1] in result["log"]]
    assert log_reports
    assert all(i and f == automix.STEMS_SHARE for f, _m, i in log_reports)
    assert result["log"][-1] == "done"


def test_a_muted_track_is_not_given_to_the_automixer(session, fake, tmp_path):
    ville = session.state.tracks[1]
    session.edit("set_track", {"track_id": ville.id, "mute": True})
    automix.run(session, {}, fake, Reports(), threading.Event())
    files = call(tmp_path)["files"]
    assert len(files) == 1
    assert "Olli" in files[0]


def test_failure_gives_a_translated_error_with_the_last_lines(
        session, fake, tmp_path, temp_root):
    fake["extra_args"] = ["--mode", "fail"]
    with pytest.raises(automix.AutomixError) as e:
        automix.run(session, {}, fake, Reports(), threading.Event())
    assert e.value.key == "error.automix.failed"
    assert e.value.params["code"] == 3
    assert "boom: no plug-in" in e.value.params["tail"]
    assert "boom: no plug-in" in str(messages.t(e.value.key, **e.value.params))
    assert list(temp_root.iterdir()) == []
    assert not list((tmp_path / "Episode exports").glob("*automixer*"))


def test_the_tail_is_at_most_fifteen_lines(session, fake):
    lines = [f"line {i}" for i in range(40)]

    def runner(_cmd, _cwd, on_line, _cancel):
        for line in lines:
            on_line(line)
        return 1

    with pytest.raises(automix.AutomixError) as e:
        automix.run(session, {}, fake, Reports(), threading.Event(), run_process=runner)
    assert e.value.params["tail"].splitlines() == lines[-15:]


def test_missing_command_is_one_clear_error(session, fake, temp_root):
    fake["command"] = ["definitely-not-an-automixer-xyz"]
    with pytest.raises(automix.AutomixError) as e:
        automix.run(session, {}, fake, Reports(), threading.Event())
    assert e.value.key == "error.automix.not_found"
    text = str(messages.t(e.value.key, **e.value.params))
    assert "definitely-not-an-automixer-xyz" in text
    assert list(temp_root.iterdir()) == []


def test_missing_working_folder_is_reported(session, fake, tmp_path):
    fake["cwd"] = str(tmp_path / "nope")
    with pytest.raises(automix.AutomixError) as e:
        automix.run(session, {}, fake, Reports(), threading.Event())
    assert e.value.key == "error.automix.bad_cwd"


def test_exit_zero_without_output_is_an_error(session, fake, temp_root):
    def runner(_cmd, _cwd, on_line, _cancel):
        on_line("fine")
        return 0

    with pytest.raises(automix.AutomixError) as e:
        automix.run(session, {}, fake, Reports(), threading.Event(), run_process=runner)
    assert e.value.key == "error.automix.no_output"
    assert list(temp_root.iterdir()) == []


def test_cancel_stops_the_process_and_removes_everything(
        session, fake, tmp_path, temp_root):
    fake["extra_args"] = ["--mode", "hang"]
    cancel = threading.Event()
    reports = Reports()

    def watch():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if any(m == "working" for _f, m, _i in reports.items):
                cancel.set()
                return
            time.sleep(0.02)

    threading.Thread(target=watch, daemon=True).start()
    started = time.monotonic()
    with pytest.raises(JobCancelledError):
        automix.run(session, {}, fake, reports, cancel)
    assert time.monotonic() - started < 20  # did not wait out the 60 s sleep
    assert list(temp_root.iterdir()) == []
    exports = tmp_path / "Episode exports"
    assert not exports.exists() or not list(exports.glob("*automixer*"))


def test_cancel_during_the_stems_export(session, fake, temp_root):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(JobCancelledError):
        automix.run(session, {}, fake, Reports(), cancel)
    assert list(temp_root.iterdir()) == []


def test_the_project_is_not_changed_and_the_export_folder_not_remembered(session, fake):
    head = session.history.head
    automix.run(session, {}, fake, Reports(), threading.Event())
    assert session.history.head == head
    assert session.export_folder_hint()["remembered"] is False
