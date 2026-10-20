"""The automixer export knows what Kuulas already did (Set music level): the
dialog's data, the flag the run sends and the log header line."""

import json
import sys
import threading
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import automix, music_level
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000
FAKE = (
    "import json, os, sys\nimport numpy as np, soundfile as sf\n"
    "a = sys.argv[1:]\n"
    "if '--help' in a:\n    print('usage\\n  --bed-under-speech-db FLOAT'); sys.exit(0)\n"
    "json.dump({'argv': a}, open(os.environ['FAKE_LOG'], 'w'))\n"
    "sf.write(a[a.index('-o') + 1], np.zeros(4800, dtype='float32'), 48000)\n")


class IdleEngine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


class Reports:
    def __call__(self, *a, **k):
        pass


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    src = tmp_path / "src"
    src.mkdir()
    paths = []
    for i, name in enumerate(("Olli", "Maija")):
        rng = np.random.default_rng(i)
        sf.write(src / f"{name}.wav", (rng.standard_normal(RATE * 2) * 0.1).astype(
            np.float32), RATE, subtype="PCM_16")
        paths.append(str(src / f"{name}.wav"))
    s.import_media(paths)
    yield s
    s.close()


def mark_done(session, offset=-10.0, key="current"):
    state = session.state
    entry = {"offset_db": offset, "speech_lufs": -20.0, "bed_lufs": -15.0,
             "mode": "common", "change_db": -5.0, "gains": {},
             "key": music_level.key(state) if key == "current" else key,
             "algorithm": music_level.ALGORITHM, "set_at": "2026-10-20T19:45:00+03:00"}
    session._commit("Set music level", replace(state, mix_done={"bed_level": entry}),
                    "set_music_level", {})


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(tmp_path / "automixer.json"))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "call.json"))
    script = tmp_path / "fake.py"
    script.write_text(FAKE, encoding="utf-8")
    automix.clear_capability_cache()
    return {"command": [sys.executable, str(script)], "cwd": str(tmp_path),
            "extra_args": []}


def test_nothing_done_gives_an_empty_answer(session):
    assert automix.done_in_kuulas(session.state) == {}


def test_a_current_record_is_reported_with_its_option(session):
    mark_done(session)
    got = automix.done_in_kuulas(session.state)["bed_level"]
    assert got["option"] == "bed_under_speech_db"
    assert (got["offset_db"], got["mode"], got["current"]) == (-10.0, "common", True)
    assert got["set_at"] == "2026-10-20T19:45:00+03:00"


def test_a_stale_record_is_reported_as_not_current(session):
    mark_done(session, key="old-key")
    assert automix.done_in_kuulas(session.state)["bed_level"]["current"] is False


def test_the_api_carries_it(session, tmp_path, settings):
    mark_done(session)
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, IdleEngine(), language="en", ui_dir=ui)) as c:
        got = c.get("/api/settings/automixer").json()
    assert got["done_in_kuulas"]["bed_level"]["offset_db"] == -10.0
    assert got["done_in_kuulas"]["bed_level"]["current"] is True


def test_the_api_has_none_for_a_project_that_never_set_it(session, tmp_path, settings):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, IdleEngine(), language="en", ui_dir=ui)) as c:
        assert c.get("/api/settings/automixer").json()["done_in_kuulas"] == {}


def run_with(session, settings, value):
    return automix.run(session, {"options": {"bed_under_speech_db": value}},
                       settings, Reports(), threading.Event())


def test_the_run_sends_the_done_offset_and_logs_it(session, settings, tmp_path):
    mark_done(session)
    result = run_with(session, settings, -10)
    argv = json.loads((tmp_path / "call.json").read_text())["argv"]
    assert argv[argv.index("--bed-under-speech-db") + 1] == "-10"
    head = Path(result["log_file"]).read_text(encoding="utf-8").partition("\n\n")[0]
    assert "Done in Kuulas: music level -10 dB (set at 2026-10-20T19:45:00+03:00)" in head


def test_a_stale_record_is_not_logged_as_done(session, settings):
    mark_done(session, key="old-key")
    result = run_with(session, settings, -10)
    assert "Done in Kuulas" not in Path(result["log_file"]).read_text(encoding="utf-8")


def test_a_value_the_user_changed_is_not_logged_as_done(session, settings):
    mark_done(session)
    result = run_with(session, settings, -6)
    assert "Done in Kuulas" not in Path(result["log_file"]).read_text(encoding="utf-8")


def test_set_music_level_stamps_when_it_was_set():
    plan = music_level.Plan(-5.0, {}, ())
    entry = music_level.record(
        {"speech_lufs": -20.0, "bed_lufs": -15.0, "key": "k"}, -10.0, plan,
        at="2026-10-20T19:45:00+03:00")
    assert entry["set_at"] == "2026-10-20T19:45:00+03:00"


# -- Level blocks: a stage Kuulas did (the switch goes off), not a number ---------


def level_blocks_done(session):
    session.command("level_blocks", {})


def test_block_level_is_a_stage_whose_value_is_off(session):
    level_blocks_done(session)
    got = automix.done_in_kuulas(session.state)["block_level"]
    assert got["option"] == "block_level"
    assert got["value"] is False
    assert got["current"] is True
    assert got["set_at"]
    # The number option keeps its shape and gains the same generic field.
    mark_done(session)
    bed = automix.done_in_kuulas(session.state)["bed_level"]
    assert (bed["value"], bed["offset_db"]) == (-10.0, -10.0)


def test_block_level_goes_stale_when_a_clip_changes(session):
    level_blocks_done(session)
    clip = session.state.tracks[0].clips[0]
    session.edit("set_clip", {"clip_id": clip.id, "gain_db": -2.0})
    assert automix.done_in_kuulas(session.state)["block_level"]["current"] is False


def test_the_registry_shape_for_a_stage():
    assert automix.DONE_IN_KUULAS["block_level"] == ("block_level", None)
    assert automix.DONE_IN_KUULAS["bed_under_speech_db"] == ("bed_level", "offset_db")


def test_the_api_carries_block_level(session, tmp_path, settings):
    level_blocks_done(session)
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, IdleEngine(), language="en", ui_dir=ui)) as c:
        got = c.get("/api/settings/automixer").json()["done_in_kuulas"]["block_level"]
    assert (got["option"], got["value"], got["current"]) == ("block_level", False, True)


def run_options(session, settings, options):
    return automix.run(session, {"options": options}, settings, Reports(),
                       threading.Event())


def test_the_run_sends_no_block_level_and_logs_it(session, settings, tmp_path):
    level_blocks_done(session)
    result = run_options(session, settings, {"block_level": False})
    argv = json.loads((tmp_path / "call.json").read_text())["argv"]
    assert "--no-block-level" in argv
    head = Path(result["log_file"]).read_text(encoding="utf-8").partition("\n\n")[0]
    assert "Done in Kuulas: block level (set at " in head


def test_block_level_left_on_or_stale_is_not_logged_as_done(session, settings):
    level_blocks_done(session)
    on = run_options(session, settings, {})
    assert "Done in Kuulas" not in Path(on["log_file"]).read_text(encoding="utf-8")
    clip = session.state.tracks[0].clips[0]
    session.edit("set_clip", {"clip_id": clip.id, "gain_db": -2.0})
    stale = run_options(session, settings, {"block_level": False})
    assert "Done in Kuulas" not in Path(stale["log_file"]).read_text(encoding="utf-8")


def test_a_number_never_matches_a_stage_value(session, settings):
    # False == 0 in Python: a music level of 0 dB must not read as "block level off".
    mark_done(session, offset=0.0)
    result = run_with(session, settings, 0)
    text = Path(result["log_file"]).read_text(encoding="utf-8")
    assert "Done in Kuulas: music level 0 dB" in text
    assert "block level" not in text
