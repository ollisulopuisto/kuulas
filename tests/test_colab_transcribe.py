"""Transcribe on Colab (WP78): the runner, with a fake ``colab-transcribe``.

The fake is a small Python script with the contract's command line: it writes
``<audio stem>.words.json`` into the ``--json`` folder and prints PROGRESS lines.
No network, no Colab."""

import json
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from kuulas import colab_transcribe as ct
from kuulas import messages
from kuulas.clock import FLICKS
from kuulas.jobs import JobCancelledError

FAKE = textwrap.dedent('''
    import json, os, sys, time
    argv = sys.argv[1:]
    if "--events" in argv and os.environ.get("FAKE_OLD"):
        print("usage: colab-transcribe [--audio F]", flush=True)
        print("colab-transcribe: error: unrecognized arguments: --events", flush=True)
        with open(os.environ["FAKE_LOG"] + ".calls", "a") as f:
            f.write(" ".join(argv) + "\\n")
        sys.exit(2)
    mode = argv[argv.index("--mode") + 1] if "--mode" in argv else "ok"
    audio = [argv[i + 1] for i, a in enumerate(argv) if a == "--audio"]
    folder = argv[argv.index("--json") + 1]
    with open(os.environ["FAKE_LOG"], "w") as f:
        json.dump({"argv": argv, "cwd": os.getcwd(), "audio": audio,
                   "folder_exists": os.path.isdir(folder)}, f)
    with open(os.environ["FAKE_LOG"] + ".calls", "a") as f:
        f.write(" ".join(argv) + "\\n")
    def ev(**kw):
        print("@@kuulas " + json.dumps({"schema": 1, **kw}), flush=True)
    if mode == "events_lost" and "--reset-session" not in argv:
        ev(event="session", state="reuse")
        ev(event="warning", code="session_lost", message="The Colab session was lost")
        print("something unrelated, no words the old text rule knows", flush=True)
        sys.exit(1)
    if mode == "events_fail":
        ev(event="stage", stage="upload", state="start")
        ev(event="error", reason="failed", message="Quota exceeded for this account",
           code=4, stage="upload")
        print("long noisy log line one", flush=True)
        print("long noisy log line two", flush=True)
        sys.exit(4)
    if mode in ("events", "events_lost"):
        ev(event="session", state="new")
        ev(event="stage", stage="upload", state="start")
        ev(event="progress", percent=40, message="Uploading the audio")
        for n, path in enumerate(audio, 1):
            stem0 = os.path.splitext(os.path.basename(path))[0]
            ev(event="stage", stage="transcribe", state="start", index=n,
               total=len(audio), name=os.path.basename(path))
        ev(event="progress", percent=80, message="Aligning")
    noise = [
        "[colab] A new version of Colab CLI is available: 0.7.5 (current: 0.7.5.dev3)",
        "[colab] Run 'colab update' to update.",
        '[colab] To silence this check, set "enable_update_check": false there',
    ]
    if mode == "noise":
        for line in noise:
            print(line, flush=True)
    if mode in ("lost", "lost_always") and (
            mode == "lost_always" or "--reset-session" not in argv):
        print("PROGRESS 0 [1/10] Preparing", flush=True)
        for line in noise:
            print(line, flush=True)
        print("[colab] Session 'whisper' appears to be lost (404/401). Cleaning up.",
              flush=True)
        sys.exit(1)
    if mode == "fail":
        print("Colab quota exceeded", flush=True)
        sys.exit(4)
    if mode == "hang":
        print("PROGRESS 5 connecting", flush=True)
        time.sleep(60)
    if mode == "sigint":
        import signal
        def stop_session(*_):
            print("stopping the Colab session", flush=True)
            open(os.environ["FAKE_LOG"] + ".stopped", "w").write("ok")
            sys.exit(0)
        signal.signal(signal.SIGINT, stop_session)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)  # the tool does not handle SIGTERM
        print("PROGRESS 5 connecting", flush=True)
        time.sleep(60)
    body = os.environ.get("FAKE_BODY")
    for n, path in enumerate(audio):
        stem = os.path.splitext(os.path.basename(path))[0]
        print(f"PROGRESS {int(100 * n / len(audio))} transcribing {stem}", flush=True)
        time.sleep(0.3)  # a real run takes minutes; the reader must see this line first
        if mode == "nothing":
            continue
        doc = json.loads(body) if body else {
            "version": 1, "timing": "whisper", "language": "fi",
            "words": [{"w": "hei", "s": 0.5, "e": 0.75},
                      {"w": "maailma", "s": 1.0, "e": 1.5}]}
        with open(os.path.join(folder, stem + ".words.json"), "w") as f:
            json.dump(doc, f)
    print("PROGRESS 100 done", flush=True)
''')


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def fake(tmp_path, monkeypatch):
    script = tmp_path / "fake_colab.py"
    script.write_text(FAKE, encoding="utf-8")
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "call.json"))
    return {"command": [sys.executable, str(script)], "cwd": str(tmp_path),
            "extra_args": []}


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setattr(ct.tempfile, "tempdir", str(root))
    return root


class Reports:
    def __init__(self):
        self.items = []

    def __call__(self, fraction, message="", *, indeterminate=False):
        self.items.append((fraction, message, indeterminate))


def files(tmp_path, *names):
    out = []
    for n in names:
        p = tmp_path / "audio" / n
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(b"x")
        out.append({"id": n.split(".")[0].lower(), "name": n, "path": p})
    return out


def run(items, fake, **kw):
    reports = kw.pop("reports", None) or Reports()
    cancel = kw.pop("cancel", None) or threading.Event()
    params = kw.pop("params", {})
    return ct.run(items, params, fake, reports, cancel, **kw), reports


def call(tmp_path) -> dict:
    return json.loads((tmp_path / "call.json").read_text())


# -- settings and the command line -------------------------------------------------------


def test_defaults():
    s = ct.resolve_settings({})
    assert s["command"] == [
        "uvx", "--from",
        "git+https://github.com/ollisulopuisto/podcast#subdirectory=colab-transcribe",
        "colab-transcribe"]
    assert s["cwd"] is None
    assert s["extra_args"] == []
    assert s["no_drive"] is False  # the plain-audio mode never uses Drive
    assert s["align"] is True  # the word starts are corrected after Whisper (--align)
    assert s["model"] == "turbo"
    assert s["language"] is None


def test_stored_values_win_and_junk_falls_back():
    s = ct.resolve_settings({"command": ["uv", "run", "colab-transcribe"], "cwd": "/p",
                             "extra_args": ["--x"], "no_drive": False, "model": "small",
                             "language": "fi"})
    assert s["command"] == ["uv", "run", "colab-transcribe"]
    assert (s["cwd"], s["extra_args"], s["no_drive"]) == ("/p", ["--x"], False)
    assert (s["model"], s["language"]) == ("small", "fi")
    s = ct.resolve_settings({"command": [], "extra_args": "x", "no_drive": "yes",
                             "model": 3, "cwd": " "})
    assert s["command"][0] == "uvx"
    assert s["extra_args"] == []
    assert s["no_drive"] is False
    assert s["model"] == "turbo"
    assert s["cwd"] is None


def test_settings_file_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_COLAB_FILE", str(tmp_path / "cfg" / "colab.json"))
    assert ct.load_settings() == {}
    stored = ct.save_settings({"command": ["colab-transcribe"], "cwd": "/p",
                               "extra_args": ["--a"], "no_drive": False, "junk": 1})
    assert stored == {"command": ["colab-transcribe"], "cwd": "/p",
                      "extra_args": ["--a"], "no_drive": False}
    assert ct.load_settings() == stored
    (tmp_path / "cfg" / "colab.json").write_text("{broken")
    assert ct.load_settings() == {}


@pytest.mark.parametrize("bad", [{"command": "uvx"}, {"command": []}, {"cwd": 3},
                                 {"extra_args": [1]}, {"no_drive": "no"}, {"model": 1}])
def test_bad_settings_are_refused(tmp_path, monkeypatch, bad):
    monkeypatch.setenv("KUULAS_COLAB_FILE", str(tmp_path / "colab.json"))
    with pytest.raises(ct.ColabError) as e:
        ct.save_settings(bad)
    assert e.value.key == "error.colab.bad_settings"


def test_command_line_is_an_argument_list():
    settings = {"command": ["uvx", "colab-transcribe"], "extra_args": ["--gpu", "L4"],
                "no_drive": True}
    cmd = ct.build_command(settings, [Path("/a/One.wav"), Path("/b/Two.flac")],
                           Path("/t/out"), model="turbo", language="fi")
    assert cmd == ["uvx", "colab-transcribe", "--audio", "/a/One.wav", "--audio",
                   "/b/Two.flac", "--json", "/t/out", "--progress", "--model", "turbo",
                   "--language", "fi", "--align", "--no-drive", "--gpu", "L4"]
    cmd = ct.build_command(
        {"command": ["c"], "extra_args": [], "no_drive": False, "align": False},
        [Path("/a/One.wav")], Path("/t"), model="small", language=None)
    assert cmd == ["c", "--audio", "/a/One.wav", "--json", "/t", "--progress",
                   "--model", "small"]


# -- the strict reader -------------------------------------------------------------------


def doc(**over):
    base = {"version": 1, "timing": "whisper", "language": "fi",
            "words": [{"w": "hei", "s": 0.5, "e": 0.75},
                      {"w": "maailma", "s": 1.0, "e": 1.5}]}
    base.update(over)
    return base


def without(key):
    return {k: v for k, v in doc().items() if k != key}


def write(tmp_path, data):
    p = tmp_path / "x.words.json"
    p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return p


def test_reader_converts_seconds_to_flicks(tmp_path):
    result = ct.read_words_json(write(tmp_path, doc()))
    assert result["timing"] == "whisper"
    assert result["language"] == "fi"
    assert result["words"] == [
        {"w": "hei", "s": round(0.5 * FLICKS), "e": round(0.75 * FLICKS), "spk": ""},
        {"w": "maailma", "s": FLICKS, "e": round(1.5 * FLICKS), "spk": ""}]


def test_reader_accepts_ctc_timing_and_an_empty_word_list(tmp_path):
    assert ct.read_words_json(write(tmp_path, doc(timing="ctc-v1")))["timing"] == "ctc-v1"
    assert ct.read_words_json(write(tmp_path, doc(words=[])))["words"] == []


def test_a_zero_length_word_gets_one_flick(tmp_path):
    r = ct.read_words_json(write(tmp_path, doc(words=[{"w": "a", "s": 1, "e": 1}])))
    assert r["words"][0]["e"] == r["words"][0]["s"] + 1


def bad_words(*items):
    return doc(words=list(items))


@pytest.mark.parametrize(("data", "key"), [
    ("{not json", "error.colab.result_unreadable"),
    ("[1, 2]", "error.colab.result_unreadable"),
    (doc(version=2), "error.colab.result_version"),
    (without("version"), "error.colab.result_version"),
    (doc(timing="magic"), "error.colab.result_timing"),
    (without("timing"), "error.colab.result_timing"),
    (without("words"), "error.colab.result_words"),
    (doc(words="hei"), "error.colab.result_words"),
    (bad_words({"s": 0, "e": 1}), "error.colab.result_word"),
    (bad_words({"w": "a", "e": 1}), "error.colab.result_word"),
    (bad_words({"w": "a", "s": 0}), "error.colab.result_word"),
    (bad_words({"w": "a", "s": "0", "e": 1}), "error.colab.result_word"),
    (bad_words({"w": "a", "s": True, "e": 1}), "error.colab.result_word"),
    (bad_words({"w": "", "s": 0, "e": 1}), "error.colab.result_word"),
    (bad_words(7), "error.colab.result_word"),
    ('{"version":1,"timing":"whisper","words":[{"w":"a","s":NaN,"e":1}]}',
     "error.colab.result_word"),
    (bad_words({"w": "a", "s": -0.5, "e": 1}), "error.colab.result_negative"),
    (bad_words({"w": "a", "s": 2, "e": 1}), "error.colab.result_end_before_start"),
    (bad_words({"w": "a", "s": 2, "e": 3}, {"w": "b", "s": 1, "e": 4}),
     "error.colab.result_order"),
])
def test_reader_rejects_each_fault_with_its_own_key(tmp_path, data, key):
    with pytest.raises(ct.ColabError) as e:
        ct.read_words_json(write(tmp_path, data))
    assert e.value.key == key
    # every key has an English text
    assert str(messages.t(e.value.key, **e.value.params)) != e.value.key


def test_reader_names_the_word_in_the_error(tmp_path):
    with pytest.raises(ct.ColabError) as e:
        ct.read_words_json(write(tmp_path, bad_words(
            {"w": "a", "s": 0, "e": 1}, {"w": "b", "s": 0.5, "e": 0.2})))
    assert e.value.params["index"] == 1


def test_missing_file_is_unreadable(tmp_path):
    with pytest.raises(ct.ColabError) as e:
        ct.read_words_json(tmp_path / "nope.words.json")
    assert e.value.key == "error.colab.result_unreadable"


# -- running -----------------------------------------------------------------------------


def test_success_one_call_for_all_files_and_cleans_up(tmp_path, fake, temp_root):
    items = files(tmp_path, "Olli.wav", "Maija.flac")
    result, reports = run(items, fake, params={"language": "fi", "model": "small"})
    assert set(result["results"]) == {"olli", "maija"}
    assert result["results"]["olli"]["timing"] == "whisper"
    assert result["results"]["olli"]["words"][0]["w"] == "hei"
    seen = call(tmp_path)
    assert seen["cwd"] == str(tmp_path)
    assert seen["audio"] == [str(i["path"]) for i in items]  # in place, no copies
    assert seen["folder_exists"]
    assert "--progress" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--model") + 1] == "small"
    assert seen["argv"][seen["argv"].index("--language") + 1] == "fi"
    assert "--no-drive" not in seen["argv"]
    assert list(temp_root.iterdir()) == []
    fractions = [r[0] for r in reports.items]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0
    assert result["log"][-1] == "PROGRESS 100 done"


def test_progress_says_which_file_it_is_on(tmp_path, fake, temp_root):
    items = files(tmp_path, "Olli.wav", "Maija.flac")
    _result, reports = run(items, fake)
    shown = [m for _f, m, _i in reports.items]
    assert any(m.startswith("[1/2] ") and "Olli" in m for m in shown)
    assert any(m.startswith("[2/2] ") and "Maija" in m for m in shown)
    # the percent the tool prints is the bar, and it never goes back
    fractions = [f for f, _m, _i in reports.items]
    assert fractions == sorted(fractions)


def test_a_failed_run_gives_the_last_lines(tmp_path, fake, temp_root):
    fake["extra_args"] = ["--mode", "fail"]
    with pytest.raises(ct.ColabError) as e:
        run(files(tmp_path, "Olli.wav"), fake)
    assert e.value.key == "error.colab.failed"
    assert e.value.params["code"] == 4
    assert "Colab quota exceeded" in str(messages.t(e.value.key, **e.value.params))
    assert list(temp_root.iterdir()) == []


def test_a_lost_colab_session_is_retried_once_with_a_fresh_one(tmp_path, fake, temp_root):
    # The tool reuses a Colab session called 'whisper'; one that died (404/401) fails the
    # run (owner, 2026-10-23, packaged app). A second try asks the tool for a new session.
    fake["extra_args"] = ["--mode", "lost"]
    result, _reports = run(files(tmp_path, "Olli.wav"), fake)
    assert result["results"]["olli"]["words"]
    calls = (tmp_path / "call.json.calls").read_text().splitlines()
    assert len(calls) == 2
    assert "--reset-session" not in calls[0]
    assert "--reset-session" in calls[1]


def test_a_session_that_stays_lost_fails_after_the_one_retry(tmp_path, fake, temp_root):
    fake["extra_args"] = ["--mode", "lost_always"]
    with pytest.raises(ct.ColabError) as e:
        run(files(tmp_path, "Olli.wav"), fake)
    assert e.value.key == "error.colab.failed"
    assert len((tmp_path / "call.json.calls").read_text().splitlines()) == 2
    assert list(temp_root.iterdir()) == []


def test_other_failures_are_not_retried(tmp_path, fake, temp_root):
    fake["extra_args"] = ["--mode", "fail"]
    with pytest.raises(ct.ColabError):
        run(files(tmp_path, "Olli.wav"), fake)
    assert len((tmp_path / "call.json.calls").read_text().splitlines()) == 1


def test_a_retry_is_not_added_when_the_user_already_resets_sessions(
        tmp_path, fake, temp_root):
    fake["extra_args"] = ["--mode", "lost_always", "--reset-session"]
    with pytest.raises(ct.ColabError):
        run(files(tmp_path, "Olli.wav"), fake)
    assert len((tmp_path / "call.json.calls").read_text().splitlines()) == 1


def test_the_colab_clis_update_notices_are_not_progress_or_error_text(
        tmp_path, fake, temp_root):
    fake["extra_args"] = ["--mode", "noise"]
    _result, reports = run(files(tmp_path, "Olli.wav"), fake)
    shown = " ".join(m for _f, m, _i in reports.items)
    assert "new version of Colab CLI" not in shown
    assert "enable_update_check" not in shown
    fake["extra_args"] = ["--mode", "lost_always", "--reset-session"]
    with pytest.raises(ct.ColabError) as e:
        run(files(tmp_path, "Olli.wav"), fake)
    text = str(messages.t(e.value.key, **e.value.params))
    assert "enable_update_check" not in text
    assert "appears to be lost" in text


def test_missing_tool_is_one_clear_error(tmp_path, fake, temp_root):
    fake["command"] = ["definitely-not-colab-transcribe-xyz"]
    with pytest.raises(ct.ColabError) as e:
        run(files(tmp_path, "Olli.wav"), fake)
    assert e.value.key == "error.colab.not_found"
    assert "definitely-not-colab-transcribe-xyz" in str(
        messages.t(e.value.key, **e.value.params))
    assert list(temp_root.iterdir()) == []


def test_missing_folder_is_reported(tmp_path, fake):
    fake["cwd"] = str(tmp_path / "nope")
    with pytest.raises(ct.ColabError) as e:
        run(files(tmp_path, "Olli.wav"), fake)
    assert e.value.key == "error.colab.bad_cwd"


def test_a_missing_result_names_the_file(tmp_path, fake, temp_root):
    fake["extra_args"] = ["--mode", "nothing"]
    with pytest.raises(ct.ColabError) as e:
        run(files(tmp_path, "Olli.wav"), fake)
    assert e.value.key == "error.colab.no_result"
    assert e.value.params["name"] == "Olli.wav"
    assert list(temp_root.iterdir()) == []


def test_a_malformed_result_names_the_file_and_leaves_no_temp(
        tmp_path, fake, temp_root, monkeypatch):
    monkeypatch.setenv("FAKE_BODY", json.dumps(doc(version=9)))
    with pytest.raises(ct.ColabError) as e:
        run(files(tmp_path, "Olli.wav"), fake)
    assert e.value.key == "error.colab.result_version"
    assert e.value.params["name"] == "Olli.wav"
    assert list(temp_root.iterdir()) == []


def test_two_files_with_one_stem_are_refused_before_anything_runs(tmp_path, fake):
    a = tmp_path / "a" / "Olli.wav"
    b = tmp_path / "b" / "Olli.flac"
    for p in (a, b):
        p.parent.mkdir()
        p.write_bytes(b"x")
    items = [{"id": "1", "name": "Olli.wav", "path": a},
             {"id": "2", "name": "Olli.flac", "path": b}]
    with pytest.raises(ct.ColabError) as e:
        run(items, fake)
    assert e.value.key == "error.colab.duplicate_names"
    assert not (tmp_path / "call.json").exists()


def test_cancel_stops_the_process_and_removes_the_folder(tmp_path, fake, temp_root):
    fake["extra_args"] = ["--mode", "hang"]
    cancel, reports = threading.Event(), Reports()

    def watch():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if any("connecting" in m for _f, m, _i in reports.items):
                cancel.set()
                return
            time.sleep(0.02)

    threading.Thread(target=watch, daemon=True).start()
    started = time.monotonic()
    with pytest.raises(JobCancelledError):
        run(files(tmp_path, "Olli.wav"), fake, reports=reports, cancel=cancel)
    assert time.monotonic() - started < 20
    assert list(temp_root.iterdir()) == []


def test_the_temp_folder_is_private(tmp_path, fake, temp_root):
    seen = {}

    def runner(cmd, _cwd, _on_line, _cancel):
        folder = Path(cmd[cmd.index("--json") + 1])
        seen["mode"] = folder.stat().st_mode & 0o777
        seen["parent"] = folder.parent
        return 1

    with pytest.raises(ct.ColabError):
        run(files(tmp_path, "Olli.wav"), fake, run_process=runner)
    assert seen["mode"] == 0o700
    assert seen["parent"] == temp_root
    assert list(temp_root.iterdir()) == []


def test_every_error_key_has_english_and_finnish_text():
    folder = Path(messages.__file__).with_name("locales")
    en = json.loads((folder / "en.json").read_text(encoding="utf-8"))
    fi = json.loads((folder / "fi.json").read_text(encoding="utf-8"))
    keys = [k for k in en if k.startswith("error.colab.")]
    assert len(keys) >= 12
    assert all(k in fi for k in keys)


def test_cancel_asks_the_tool_to_stop_its_colab_session_with_sigint_first(
        tmp_path, fake, temp_root):
    """The tool stops the Colab session on SIGINT; SIGTERM is not handled (the podcast
    session's answer), so a plain SIGTERM would leave the session billing."""
    fake["extra_args"] = ["--mode", "sigint"]
    cancel, reports = threading.Event(), Reports()

    def watch():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if any("connecting" in m for _f, m, _i in reports.items):
                cancel.set()
                return
            time.sleep(0.02)

    threading.Thread(target=watch, daemon=True).start()
    with pytest.raises(JobCancelledError):
        run(files(tmp_path, "Olli.wav"), fake, reports=reports, cancel=cancel)
    assert (tmp_path / "call.json.stopped").read_text() == "ok"
    assert list(temp_root.iterdir()) == []


@pytest.mark.parametrize("timing", ["whisper", "ctc-v1", "ctc-v2", "ctc-v10"])
def test_known_timing_values_including_future_aligner_versions(
        tmp_path, fake, temp_root, monkeypatch, timing):
    monkeypatch.setenv("FAKE_BODY", json.dumps(doc(timing=timing)))
    result, _ = run(files(tmp_path, "Olli.wav"), fake)
    assert result["results"]["olli"]["timing"] == timing


@pytest.mark.parametrize("timing", ["ctc", "ctc-v", "CTC-v1", "ctc-vx", "other", 1])
def test_other_timing_values_are_refused(tmp_path, fake, temp_root, monkeypatch, timing):
    monkeypatch.setenv("FAKE_BODY", json.dumps(doc(timing=timing)))
    with pytest.raises(ct.ColabError) as info:
        run(files(tmp_path, "Olli.wav"), fake)
    assert info.value.key == "error.colab.result_timing"


def test_the_rejected_count_of_a_corrected_transcript_is_passed_on(
        tmp_path, fake, temp_root, monkeypatch):
    monkeypatch.setenv("FAKE_BODY", json.dumps(doc(timing="ctc-v1", rejected=3)))
    result, _ = run(files(tmp_path, "Olli.wav"), fake)
    assert result["results"]["olli"]["rejected"] == 3
    monkeypatch.setenv("FAKE_BODY", json.dumps(doc()))
    result, _ = run(files(tmp_path, "Olli.wav"), fake)
    assert result["results"]["olli"]["rejected"] == 0


def test_the_command_asks_for_the_word_start_correction_by_default():
    cmd = ct.build_command(ct.resolve_settings({"command": ["c"]}), [Path("a.wav")],
                           Path("/o"), model="turbo", language=None)
    assert "--align" in cmd
    assert cmd.index("--align") > cmd.index("--progress")


def test_the_correction_can_be_switched_off_and_junk_means_on():
    off = ct.resolve_settings({"align": False})
    assert off["align"] is False
    assert ct.resolve_settings({"align": "no"})["align"] is True
    cmd = ct.build_command({**off, "command": ["c"]}, [Path("a.wav")], Path("/o"),
                           model="m", language=None)
    assert "--align" not in cmd


def test_align_is_a_stored_setting(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_COLAB_FILE", str(tmp_path / "colab.json"))
    assert ct.save_settings({"align": False}) == {"align": False}
    with pytest.raises(ct.ColabError):
        ct.save_settings({"align": "yes"})


# -- the tool's --events (podcast PR #83; BUGS #107) ------------------------------------


def test_the_events_flag_is_asked_for(tmp_path, fake, temp_root):
    ct.forget_event_support()
    run(files(tmp_path, "Olli.wav"), fake)
    assert "--events" in call(tmp_path)["argv"]


def test_a_tool_that_refuses_the_flag_is_run_again_without_it_and_remembered(
        tmp_path, fake, temp_root, monkeypatch):
    ct.forget_event_support()
    monkeypatch.setenv("FAKE_OLD", "1")
    result, _reports = run(files(tmp_path, "Olli.wav"), fake)
    assert result["results"]["olli"]["words"]
    calls = (tmp_path / "call.json.calls").read_text().splitlines()
    assert len(calls) == 2
    assert "--events" in calls[0]
    assert "--events" not in calls[1]
    run(files(tmp_path, "Olli.wav"), fake)  # remembered: no second refusal
    assert len((tmp_path / "call.json.calls").read_text().splitlines()) == 3


def test_progress_and_stage_events_drive_the_bar_and_the_text(tmp_path, fake, temp_root):
    fake["extra_args"] = ["--mode", "events"]
    _result, reports = run(files(tmp_path, "Olli.wav", "Maija.flac"), fake)
    shown = [m for _f, m, _i in reports.items]
    fractions = [f for f, _m, _i in reports.items]
    assert any("Uploading the audio" in m for m in shown)
    assert any("Olli.wav" in m and "1/2" in m for m in shown)
    assert any("Maija.flac" in m and "2/2" in m for m in shown)
    assert max(fractions) >= 0.79 * 0.99
    assert fractions == sorted(fractions)


def test_event_lines_are_not_part_of_the_log(tmp_path, fake, temp_root):
    fake["extra_args"] = ["--mode", "events"]
    result, _reports = run(files(tmp_path, "Olli.wav"), fake)
    assert not any(line.startswith("@@kuulas") for line in result["log"])


def test_an_error_event_gives_the_short_reason_not_the_log(tmp_path, fake, temp_root):
    fake["extra_args"] = ["--mode", "events_fail"]
    with pytest.raises(ct.ColabError) as e:
        run(files(tmp_path, "Olli.wav"), fake)
    assert e.value.key == "error.colab.failed"
    assert e.value.params["code"] == 4
    assert e.value.params["tail"] == "Quota exceeded for this account"


def test_a_session_lost_warning_triggers_the_retry_by_its_code(tmp_path, fake, temp_root):
    fake["extra_args"] = ["--mode", "events_lost"]
    result, _reports = run(files(tmp_path, "Olli.wav"), fake)
    assert result["results"]["olli"]["words"]
    calls = (tmp_path / "call.json.calls").read_text().splitlines()
    assert len(calls) == 2
    assert "--reset-session" in calls[1]
