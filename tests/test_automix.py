"""Mix with the automixer (WP68 step 1): the runner, with a fake automixer.

The fake is a tiny Python script that takes the automixer's command line, writes
a wav to ``-o`` and prints progress. No real automixer, no audio playback."""

import contextlib
import json
import shlex
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
    positional, i = [], 0
    while i < len(argv):
        if argv[i] in valued:
            i += 2
        elif argv[i].startswith("--"):
            i += 1
        else:
            positional.append(argv[i])
            i += 1
    files = []
    if len(positional) == 1 and os.path.isdir(positional[0]):
        listing = json.load(open(os.path.join(positional[0], "tracks.json")))
        files = [os.path.join(positional[0], t["file"])
                 for t in listing["tracks"] if t["audible"]]
    with open(os.environ["FAKE_LOG"], "w") as f:
        json.dump({"argv": argv, "positional": positional, "files": files,
                   "cwd": os.getcwd(),
                   "exists": [os.path.exists(p) for p in files]}, f)
    # the real automixer writes "<output without extension> flags.txt" (places to
    # listen to), empty or not
    with open(os.path.splitext(out)[0] + " flags.txt", "w") as flags:
        flags.write(os.environ.get("FAKE_FLAGS", ""))
    print("loading", len(files), "tracks", flush=True)
    if mode == "fail":
        print("boom: no plug-in", flush=True)
        sys.exit(3)
    if mode == "hang":
        sf.write(out, np.zeros(100, dtype="float32"), 48000)
        print("working", flush=True)
        time.sleep(60)
    assert "--progress" in argv
    for pct, msg in ((25, "Engine: speech"), (10, "late old line"), (50, "Engine: music"),
                     (75, "Engine: master")):
        print(f"PROGRESS {pct} {msg}", flush=True)
    print("some other line", flush=True)
    print("beds: loudest -20.1 LUFS, speech -18.0 -> beds +2.1 dB", flush=True)
    sf.write(out, np.zeros(4800, dtype="float32"), 48000)
    print("PROGRESS 100 done", flush=True)
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
    # the stems FOLDER is the one positional argument: a file list would take the
    # automixer's in-memory route
    cmd = automix.build_command(
        settings, Path("/s/stems"), Path("/o/out.wav"),
        target_lufs=-16, ad_spot=None, ad_duration=None)
    assert cmd == ["uv", "run", "automixer", "/s/stems",
                   "-o", "/o/out.wav", "--target-lufs", "-16", "--progress",
                   "--speech-plugins", "dxRevive"]
    cmd = automix.build_command(
        {"command": ["automixer"], "extra_args": []}, Path("/s/stems"),
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
    assert out.parent == tmp_path  # beside Episode.kuulas, no exports folder
    assert not (tmp_path / "Episode exports").exists()
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
    # one positional argument: the folder that holds tracks.json
    assert len(seen["positional"]) == 1
    assert (Path(seen["positional"][0]) / "tracks.json").name == "tracks.json"
    assert "--progress" in seen["argv"]
    # PROGRESS <0-100> <message> lines are the bar; the message is what follows
    mix = [(f, m, i) for f, m, i in reports.items if "Engine" in m]
    # each line starts with the step numbers ("2/4 ")
    assert [m.split(" ", 1)[1] for _f, m, _i in mix] == [
        "Engine: speech", "Engine: music", "Engine: master"]
    assert all(not i for _f, _m, i in mix)
    assert mix[0][0] == pytest.approx(0.4 + 0.6 * 0.99 * 0.25)
    # a lower percentage after a higher one never moves the bar back
    late = [f for f, m, _i in reports.items if m.endswith("late old line")]
    assert late == [mix[0][0]]
    # other lines are the message, and the bar stays where it was
    other = [r for r in reports.items if r[1].endswith("some other line")]
    assert other
    assert other[0][0] == mix[-1][0]
    assert result["log"][-1] == "PROGRESS 100 done"


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
    assert [p.name for p in tmp_path.glob("* automixer *")] == [
        Path(e.value.params["log_file"]).name]
    assert " FAILED log" in e.value.params["log_file"]


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
            if any(m.endswith("working") for _f, m, _i in reports.items):
                cancel.set()
                return
            time.sleep(0.02)

    threading.Thread(target=watch, daemon=True).start()
    started = time.monotonic()
    with pytest.raises(JobCancelledError):
        automix.run(session, {}, fake, reports, cancel)
    assert time.monotonic() - started < 20  # did not wait out the 60 s sleep
    assert list(temp_root.iterdir()) == []
    assert not list(tmp_path.glob("* automixer *"))


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


def test_an_empty_flags_file_is_not_left_behind(session, fake, tmp_path, temp_root):
    result = automix.run(session, {}, fake, Reports(), threading.Event())
    folder = Path(result["path"]).parent
    mixes = sorted(p.name for p in folder.glob("* automixer *.wav"))
    assert mixes == [Path(result["path"]).name]
    assert not list(folder.glob("*flags*"))


def test_flags_with_content_are_kept_beside_the_mix(
        session, fake, tmp_path, temp_root, monkeypatch):
    monkeypatch.setenv("FAKE_FLAGS", "12.5 s: check this\n")
    result = automix.run(session, {}, fake, Reports(), threading.Event())
    out = Path(result["path"])
    kept = out.with_name(f"{out.stem} flags.txt")
    assert kept.read_text(encoding="utf-8") == "12.5 s: check this\n"
    assert result["flags"] == str(kept)
    assert not list(out.parent.glob("*partial*"))


def test_a_failed_run_leaves_no_flags_file(session, fake, tmp_path, temp_root):
    fake["extra_args"] = ["--mode", "fail"]
    with pytest.raises(automix.AutomixError):
        automix.run(session, {}, fake, Reports(), threading.Event())
    assert not list(tmp_path.glob("* automixer *.wav"))
    assert not list(tmp_path.glob("*flags*"))
    assert not list(tmp_path.glob("*partial*"))


def test_the_tool_does_not_inherit_the_callers_virtual_env(tmp_path, monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "/some/other/.venv")
    lines = []
    code = automix.run_process(
        [sys.executable, "-c", "import os; print(os.environ.get('VIRTUAL_ENV'))"],
        str(tmp_path), lines.append, threading.Event())
    assert code == 0
    assert lines == ["None"]


def test_the_temporary_stems_go_to_the_chosen_folder_and_are_removed(
        session, fake, tmp_path, temp_root):
    chosen = tmp_path / "bigdisk"
    chosen.mkdir()
    fake["temp_dir"] = str(chosen)
    automix.run(session, {}, fake, Reports(), threading.Event())
    stems = Path(call(tmp_path)["positional"][0])
    assert stems.parent.parent == chosen
    assert stems.parent.name.startswith("kuulas-automix-")
    assert list(chosen.iterdir()) == []  # removed afterwards
    assert list(temp_root.iterdir()) == []  # the system folder was not used


def test_without_a_chosen_folder_the_system_temporary_folder_is_used(
        session, fake, tmp_path, temp_root):
    automix.run(session, {}, fake, Reports(), threading.Event())
    stems = Path(call(tmp_path)["positional"][0])
    assert stems.parent.parent == temp_root


def test_the_scratch_folder_is_private_to_the_user(session, fake, tmp_path):
    chosen = tmp_path / "bigdisk"
    chosen.mkdir()
    fake["temp_dir"] = str(chosen)
    seen = {}

    def runner(cmd, cwd, on_line, cancel):
        stems = next(a for a in cmd if "kuulas-automix-" in a)
        seen["mode"] = Path(stems).parent.stat().st_mode & 0o777
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"RIFF")
        return 0

    automix.run(session, {}, fake, Reports(), threading.Event(), run_process=runner)
    assert seen["mode"] == 0o700


def test_a_missing_temporary_folder_is_one_clear_error(session, fake, tmp_path):
    fake["temp_dir"] = str(tmp_path / "gone")
    with pytest.raises(automix.AutomixError) as info:
        automix.run(session, {}, fake, Reports(), threading.Event())
    assert info.value.key == "error.automix.bad_temp_dir"


def test_the_temporary_folder_is_a_setting(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(tmp_path / "automixer.json"))
    assert automix.resolve_settings({}, home=tmp_path)["temp_dir"] is None
    saved = automix.save_settings({"temp_dir": "/Volumes/Big/tmp"})
    assert saved == {"temp_dir": "/Volumes/Big/tmp"}
    assert automix.resolve_settings(automix.load_settings(), home=tmp_path)[
        "temp_dir"] == "/Volumes/Big/tmp"
    with pytest.raises(automix.AutomixError):
        automix.save_settings({"temp_dir": 5})


def test_the_mix_lands_beside_the_project_package_not_in_the_remembered_export_folder(
        session, fake, tmp_path, temp_root):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    session.history.set_meta_json("export", {"folder": str(elsewhere)})
    result = automix.run(session, {}, fake, Reports(), threading.Event())
    out = Path(result["path"])
    assert out.parent == session.package.path.parent
    assert not out.is_relative_to(session.package.path)
    assert not list(elsewhere.iterdir())


def test_an_output_folder_setting_overrides_the_default(
        session, fake, tmp_path, temp_root):
    chosen = tmp_path / "mixes" / "episode"
    fake["output_dir"] = str(chosen)
    result = automix.run(session, {}, fake, Reports(), threading.Event())
    assert Path(result["path"]).parent == chosen
    assert not list(tmp_path.glob("* automixer *"))


def test_the_output_folder_is_a_setting(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(tmp_path / "automixer.json"))
    assert automix.resolve_settings({}, home=tmp_path)["output_dir"] is None
    assert automix.save_settings({"output_dir": "/Volumes/Mixes"}) == {
        "output_dir": "/Volumes/Mixes"}
    with pytest.raises(automix.AutomixError):
        automix.save_settings({"output_dir": 3})


def test_the_log_is_kept_beside_the_mix(session, fake, tmp_path, temp_root):
    result = automix.run(session, {}, fake, Reports(), threading.Event())
    out = Path(result["path"])
    kept = out.with_name(f"{out.stem} log.txt")
    assert result["log_file"] == str(kept)
    text = kept.read_text(encoding="utf-8")
    head, _, rest = text.partition("\n\n")
    assert "kuulas " in head
    assert "Episode" in head
    assert shlex.join(result["command"]) in head
    assert "Speaker balance maximum: 6 dB (Automatic)" in head
    assert "loading 2 tracks" in rest
    assert "beds: loudest -20.1 LUFS, speech -18.0 -> beds +2.1 dB" in rest
    assert "\x1b" not in text
    assert "exit code: 0" in rest.lower()
    assert str(Path.home()) in text or str(tmp_path) in text  # not redacted in the file
    assert result["summary"] == ["beds: loudest -20.1 LUFS, speech -18.0 -> beds +2.1 dB"]


def test_a_failed_run_keeps_a_log_to_diagnose(session, fake, tmp_path, temp_root):
    fake["extra_args"] = ["--mode", "fail"]
    with pytest.raises(automix.AutomixError) as e:
        automix.run(session, {}, fake, Reports(), threading.Event())
    kept = Path(e.value.params["log_file"])
    assert kept.parent == tmp_path
    assert kept.name.endswith(" FAILED log.txt")
    text = kept.read_text(encoding="utf-8")
    assert "boom: no plug-in" in text
    assert "exit code: 3" in text.lower()
    assert list(temp_root.iterdir()) == []


def test_a_log_never_overwrites_another(session, fake, tmp_path, temp_root, monkeypatch):
    when = "2026-01-01 10-00-00"
    monkeypatch.setattr(automix.export_names, "stamp", lambda _when: when)
    old = tmp_path / f"Episode automixer {when} log.txt"
    old.write_text("earlier", encoding="utf-8")
    result = automix.run(session, {}, fake, Reports(), threading.Event())
    assert old.read_text(encoding="utf-8") == "earlier"
    assert Path(result["log_file"]).name == f"Episode automixer {when} log (2).txt"
    assert Path(result["log_file"]).is_file()


def test_cancel_leaves_no_partial_log(session, fake, tmp_path, temp_root):
    fake["extra_args"] = ["--mode", "hang"]
    cancel = threading.Event()
    reports = Reports()

    def watch():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if any(m.endswith("working") for _f, m, _i in reports.items):
                cancel.set()
                return
            time.sleep(0.02)

    threading.Thread(target=watch, daemon=True).start()
    with pytest.raises(JobCancelledError):
        automix.run(session, {}, fake, reports, cancel)
    assert not list(tmp_path.glob("*log*"))
    assert not list(tmp_path.glob("* automixer *"))


def test_a_missing_tool_keeps_a_failed_log_too(session, fake, tmp_path, temp_root):
    fake["command"] = ["definitely-not-an-automixer-xyz"]
    with pytest.raises(automix.AutomixError) as e:
        automix.run(session, {}, fake, Reports(), threading.Event())
    kept = Path(e.value.params["log_file"])
    assert "definitely-not-an-automixer-xyz" in kept.read_text(encoding="utf-8")


def test_the_job_remembers_the_log_for_reveal(
        session, fake, tmp_path, temp_root, monkeypatch):
    monkeypatch.setattr(automix, "load_settings", lambda: fake)
    job = session.automix({})[0]
    def item():
        return next(j for j in session.jobs.list() if j["id"] == job)

    deadline = time.monotonic() + 30
    while item()["state"] not in ("completed", "failed"):
        assert time.monotonic() < deadline
        time.sleep(0.05)
    assert session.last_automix_log
    assert session.last_automix_log == item()["result"]["log_file"]


# -- the live log (the viewer opened while the automixer runs) ------------------------


def _quiet(fn):
    with contextlib.suppress(JobCancelledError):
        fn()


def test_run_hands_every_line_to_the_live_callback_in_order(session, fake, temp_root):
    live: list[str] = []
    result = automix.run(
        session, {}, fake, Reports(), threading.Event(), live=live.append)
    assert live[0] == "loading 2 tracks"
    assert live[-1] == "PROGRESS 100 done"
    assert live == result["log"]


def test_live_lines_arrive_while_the_tool_still_runs(session, fake, temp_root):
    seen = threading.Event()
    live: list[str] = []

    def note(line):
        live.append(line)
        if line == "working":
            seen.set()

    fake["extra_args"] = ["--mode", "hang"]
    cancel = threading.Event()
    worker = threading.Thread(target=lambda: _quiet(
        lambda: automix.run(session, {}, fake, Reports(), cancel, live=note)))
    worker.start()
    assert seen.wait(30)
    assert live[-1] == "working"  # the tool is still hanging
    cancel.set()
    worker.join(30)


def test_live_gets_the_kuulas_notes_too(session, fake, temp_root):
    live: list[str] = []

    def runner(cmd, cwd, on_line, cancel):
        on_line("hello")
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"x")
        return 0

    result = automix.run(session, {}, fake, Reports(), threading.Event(),
                         run_process=runner, live=live.append)
    assert live == result["log"]
    assert "hello" in live


def test_a_missing_tool_is_in_the_live_lines(session, fake, temp_root):
    fake["command"] = ["definitely-not-an-automixer-xyz"]
    live: list[str] = []
    with pytest.raises(automix.AutomixError):
        automix.run(session, {}, fake, Reports(), threading.Event(), live=live.append)
    assert any(line.startswith("not found") for line in live)


def test_without_live_nothing_changes(session, fake, temp_root):
    result = automix.run(session, {}, fake, Reports(), threading.Event())
    assert result["log"][0] == "loading 2 tracks"
    text = Path(result["log_file"]).read_text(encoding="utf-8")
    assert "loading 2 tracks" in text
    assert "PROGRESS 100 done" in text
