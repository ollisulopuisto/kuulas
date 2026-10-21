"""Relink a clip's media to an edited copy of the file (owner, 2026-10-21).

The use case: the user cleans a recording in another program and saves it under the same
or another name. Its SHA-256 differs, so "Locate media" (which matches by content) cannot
take it. "Locate / Relink media…" on a clip imports the chosen file as new media (linked
where it lies: the original file is never overwritten or deleted, PLAN rule 17), reports
the two lengths so the page can confirm (and warn when they differ), and then one edit,
``replace_clip_media``, points every clip of the old media at the new one: one undo step.
The same file (same hash) is a plain relink and no edit.
"""

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import messages, ops
from kuulas.clock import frames_to_flicks
from kuulas.media import MediaError
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


def wav(path, seconds, seed=1):
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(int(seconds * RATE)) * 0.1).astype(np.float32),
             RATE, subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    s = Session(tmp_path / "Talk.kuulas")
    s.import_media([str(wav(src / "a.wav", 10))])
    media_id = s.state.media[0].id
    clip = s.state.tracks[0].clips[0]
    # Two clips of the same recording: a split.
    s.edit("split_clip", {"clip_id": clip.id, "at": 4 * RATE})
    s.src = src
    s.media_id = media_id
    yield s
    s.close()


class _NoEngine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


@pytest.fixture
def client(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, _NoEngine(), language="en", ui_dir=ui)) as c:
        yield c


def test_check_imports_an_edited_copy_and_reports_both_lengths(session):
    cleaned = wav(session.src / "a (cleaned).wav", 10, seed=2)
    before = cleaned.read_bytes()
    original = (session.src / "a.wav").read_bytes()
    nodes = len(session.history.nodes())
    report = session.check_replace_media(session.media_id, str(cleaned))
    assert report["same_file"] is False
    assert report["new_media_id"] != session.media_id
    assert report["old_frames"] == report["new_frames"] == 10 * RATE
    assert report["same_length"] is True
    assert report["clips"] == 2
    # Nothing on the timeline changed yet, and neither file was touched.
    assert len(session.history.nodes()) == nodes
    assert {c.media for c in session.state.tracks[0].clips} == {session.media_id}
    assert cleaned.read_bytes() == before
    assert (session.src / "a.wav").read_bytes() == original


def test_a_different_length_is_reported(session):
    longer = wav(session.src / "a long.wav", 12, seed=3)
    report = session.check_replace_media(session.media_id, str(longer))
    assert report["same_length"] is False
    assert report["new_frames"] == 12 * RATE


def test_the_same_file_elsewhere_is_a_plain_relink_and_no_edit(session, tmp_path):
    moved = tmp_path / "moved"
    moved.mkdir()
    copy = moved / "a.wav"
    copy.write_bytes((session.src / "a.wav").read_bytes())
    nodes = len(session.history.nodes())
    report = session.check_replace_media(session.media_id, str(copy))
    assert report["same_file"] is True
    assert report["new_media_id"] == session.media_id
    assert len(session.history.nodes()) == nodes


def test_replace_points_every_clip_at_the_new_media_in_one_undo_step(session):
    cleaned = wav(session.src / "a (cleaned).wav", 10, seed=2)
    report = session.check_replace_media(session.media_id, str(cleaned))
    nodes = len(session.history.nodes())
    session.edit("replace_clip_media", {"media_id": session.media_id,
                                        "new_media_id": report["new_media_id"]})
    clips = session.state.tracks[0].clips
    assert {c.media for c in clips} == {report["new_media_id"]}
    assert [(c.start, c.offset, c.length) for c in clips] == [
        (0, 0, 4 * RATE), (4 * RATE, 4 * RATE, 6 * RATE)]
    assert len(session.history.nodes()) == nodes + 1
    session.undo()
    assert {c.media for c in session.state.tracks[0].clips} == {session.media_id}
    # The old media stays in the project's media (its file is not deleted).
    assert any(m.id == session.media_id for m in session.state.media)


def test_replace_refuses_unknown_media_and_a_no_op(session):
    p = session.state
    with pytest.raises(ops.EditError):
        ops.replace_clip_media(p, session.media_id, "nope")
    with pytest.raises(ops.EditError):
        ops.replace_clip_media(p, "nope", session.media_id)
    with pytest.raises(ops.EditError):
        ops.replace_clip_media(p, session.media_id, session.media_id)


def test_check_refuses_a_file_that_is_not_there(session):
    with pytest.raises(MediaError, match=r"missing\.wav"):
        session.check_replace_media(session.media_id, str(session.src / "missing.wav"))


def test_check_route(client, session):
    cleaned = wav(session.src / "b.wav", 10, seed=4)
    r = client.post("/api/media/replace-check",
                    json={"media_id": session.media_id, "path": str(cleaned)})
    assert r.status_code == 200
    body = r.json()
    assert body["same_length"] is True
    assert body["same_file"] is False
    r = client.post("/api/edit", json={"op": "replace_clip_media", "args": {
        "media_id": session.media_id, "new_media_id": body["new_media_id"]}})
    assert r.status_code == 200
    assert {c.media for c in session.state.tracks[0].clips} == {body["new_media_id"]}


def _words():
    """Four 2-second words, one every 3 s over the 10 s recording (flicks)."""
    return [{"w": f"w{i}", "s": frames_to_flicks(i * 3 * RATE, RATE),
             "e": frames_to_flicks((i * 3 + 2) * RATE, RATE)} for i in range(4)]


def _replace(session, seconds, seed):
    session.history.add_transcript(session.media_id, _words())
    new = wav(session.src / f"n{seconds}.wav", seconds, seed=seed)
    report = session.check_replace_media(session.media_id, str(new))
    nodes = len(session.history.nodes())
    session.edit("replace_clip_media", {"media_id": session.media_id,
                                        "new_media_id": report["new_media_id"]})
    return report["new_media_id"], nodes


def test_replace_carries_the_words_in_the_same_undo_step(session):
    new_id, nodes = _replace(session, 10, 2)
    assert len(session.history.nodes()) == nodes + 1
    words = session.transcripts()
    assert [w["w"] for w in words[new_id]] == ["w0", "w1", "w2", "w3"]
    assert [w["w"] for w in words[session.media_id]] == ["w0", "w1", "w2", "w3"]
    session.undo()
    assert new_id not in session.transcripts()
    assert session.media_id in session.transcripts()


def test_a_shorter_new_media_keeps_only_the_words_inside_it(session):
    new_id, _ = _replace(session, 7, 5)
    got = session.transcripts()[new_id]
    assert [w["w"] for w in got] == ["w0", "w1", "w2"]
    assert all(w["e"] <= frames_to_flicks(7 * RATE, RATE) for w in got)
    # The old media keeps all its words.
    assert len(session.transcripts()[session.media_id]) == 4


def test_a_new_media_that_has_words_keeps_them(session):
    new = wav(session.src / "n.wav", 10, seed=9)
    report = session.check_replace_media(session.media_id, str(new))
    mine = [{"w": "mine", "s": 0, "e": 1}]
    session.history.add_transcript(report["new_media_id"], mine)
    session.history.add_transcript(session.media_id, _words())
    session.edit("replace_clip_media", {"media_id": session.media_id,
                                        "new_media_id": report["new_media_id"]})
    assert session.transcripts()[report["new_media_id"]] == mine


def test_locate_media_no_longer_lists_a_replaced_missing_media(session):
    (session.src / "a.wav").unlink()
    assert [m["id"] for m in session.media_status()["missing"]] == [session.media_id]
    new = wav(session.src / "n.wav", 10, seed=2)
    report = session.check_replace_media(session.media_id, str(new))
    session.edit("replace_clip_media", {"media_id": session.media_id,
                                        "new_media_id": report["new_media_id"]})
    assert session.media_status()["missing"] == []
    session.undo()
    assert [m["id"] for m in session.media_status()["missing"]] == [session.media_id]
