"""The editing core loop, end to end, on a synthetic three-speaker episode.

Olli, Kari and Panu each have their own continuous tone (220, 330, 440 Hz,
12 s) and a transcript with known word times. Kari's first word overlaps
Olli's last one (crosstalk). The project comes in through a real ``.nhsx``
import and is then driven with the same commands the UI sends: ``/api/edit``,
``/api/command``, ``/api/clipboard/copy``, ``/api/undo``, ``/api/export``.

Nothing here plays audio. What cannot be covered is the browser side (key
handling, selection, the transcript view); see the report with this test.
"""

import json
import math
import os
import shutil
import socket
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import transcript
from kuulas.clipboard_store import ClipboardStore, default_path
from kuulas.messages import KuulasError
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48_000
SECONDS = 12
TOLERANCE = 3  # frames: flicks -> frames rounding of word times

#: speaker -> (tone Hz, words as (text, start s, end s) on the recording clock)
SPEAKERS = {
    "Olli": (220, [("Hei", 0.0, 0.5), ("tämä", 1.0, 1.5), ("on", 2.0, 2.5),
                   ("jakso", 3.0, 3.5), ("neljä", 4.0, 4.5)]),
    "Kari": (330, [("Moi", 4.2, 4.7), ("kiitos", 5.5, 6.0), ("kysymys", 6.5, 7.0),
                   ("vastaus", 7.5, 8.0)]),
    "Panu": (440, [("No", 8.2, 8.7), ("juu", 9.5, 10.0), ("totta", 10.5, 11.0),
                   ("loppu", 11.5, 11.9)]),
}


class Engine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


class Env:
    def __init__(self, folder: Path, source: Path, clipboard: ClipboardStore):
        self.folder, self.source, self.clipboard = folder, source, clipboard
        self.session = Session(folder, clipboard=clipboard)
        self.client = TestClient(create_app(self.session, Engine()))

    # -- the UI's doors ----------------------------------------------------
    def edit(self, op: str, **args):
        r = self.client.post("/api/edit", json={"op": op, "args": args})
        assert r.status_code == 200, r.text
        return r.json()

    def command(self, name: str, **args):
        r = self.client.post("/api/command", json={"name": name, "args": args})
        assert r.status_code == 200, r.text
        return r.json()

    def post(self, path: str, **body):
        r = self.client.post(path, json=body)
        assert r.status_code == 200, r.text
        return r.json()

    def undo(self):
        return self.post("/api/undo")

    def redo(self):
        return self.post("/api/redo")

    # -- reading the state -------------------------------------------------
    @property
    def p(self):
        return self.session.state

    def track(self, name: str):
        return next(t for t in self.p.tracks if t.name == name)

    def words(self) -> list[dict]:
        return self.session.timeline_words()

    def word(self, text: str) -> dict:
        return next(w for w in self.words() if w["w"] == text)

    def index(self, *texts: str) -> list[int]:
        ws = self.words()
        return [next(i for i, w in enumerate(ws) if w["w"] == t) for t in texts]

    def snapshot(self) -> str:
        return json.dumps(self.p.to_dict(), sort_keys=True)


def write_tone(path: Path, hz: int) -> None:
    t = np.arange(SECONDS * RATE) / RATE
    sf.write(path, (0.3 * np.sin(2 * math.pi * hz * t)).astype(np.float32), RATE,
             subtype="PCM_16")


def write_nhsx(path: Path) -> None:
    files, tracks = [], []
    for n, (name, (hz, words)) in enumerate(SPEAKERS.items(), start=1):
        write_tone(path.parent / f"{name}.wav", hz)
        ws = "".join(f'<w s="{s:.3f}" l="{e - s:.3f}" sp="{name}">{w}</w>'
                     for w, s, e in words)
        files.append(f'<File Id="{n}" Name="{name}.wav" Path="{name}.wav">'
                     f"<Transcription><p>{ws}</p></Transcription></File>")
        tracks.append(f'<Track Name="{name}"><Region Ref="{n}" Start="0.000" '
                      f'Length="{SECONDS}.000" Offset="0.000"/></Track>')
    path.write_text(f"<Session><AudioPool>{''.join(files)}</AudioPool>"
                    f"<Tracks>{''.join(tracks)}</Tracks></Session>", encoding="utf-8")


@pytest.fixture
def env(tmp_path):
    source = tmp_path / "episode.nhsx"
    write_nhsx(source)
    made = []

    def make(folder: Path | None = None) -> Env:
        e = Env(folder or tmp_path / "Episode.kuulas", source,
                ClipboardStore(default_path()))
        made.append(e)
        return e

    e = make()
    e.command("import_nhsx", path=str(source))
    yield e
    for each in made:
        each.session.close()


@pytest.fixture
def make(tmp_path, env):
    """Open more sessions on the same folder (reopen tests)."""
    opened = []

    def again(folder=None):
        e = Env(folder or env.folder, env.source, env.clipboard)
        opened.append(e)
        return e

    yield again
    for e in opened:
        e.session.close()


def near(a: int, b: int, tol: int = TOLERANCE) -> bool:
    return abs(a - b) <= tol


def clips_of(env: Env, name: str):
    return env.track(name).clips


def rms(a: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(a)))) if a.size else 0.0


def wav(path) -> np.ndarray:
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    assert rate == RATE
    return data[:, 0]


def seconds(x: float) -> int:
    return round(x * RATE)


# -- 1. import ----------------------------------------------------------------


def test_import_gives_three_tracks_clips_and_a_transcript_per_speaker(env):
    assert [t.name for t in env.p.tracks] == ["Olli", "Kari", "Panu"]
    assert all(len(t.clips) == 1 and t.clips[0].length == SECONDS * RATE
               for t in env.p.tracks)
    assert env.p.length == SECONDS * RATE
    words = env.words()
    assert len(words) == 13
    by_speaker = {n: [w["w"] for w in words if w["spk"] == n] for n in SPEAKERS}
    assert by_speaker == {n: [w for w, _, _ in ws] for n, (_, ws) in SPEAKERS.items()}
    # Each word sits on its own speaker's track, at its known time.
    kari = env.track("Kari").id
    assert {w["track"] for w in words if w["spk"] == "Kari"} == {kari}
    assert near(env.word("kiitos")["s"], seconds(5.5))
    # Crosstalk: Kari's first word overlaps Olli's last on the timeline.
    assert env.word("Moi")["s"] < env.word("neljä")["e"]
    assert not any(w["muted"] for w in words)


# -- 2. deleting words ----------------------------------------------------------


def x_cut(env: Env, *texts: str):
    """The transcript's X as the UI sends it: copy the stretch of every track to
    the clipboard, then ``cut_words`` (ui/transcript-commands.js)."""
    idx = env.index(*texts)
    ws = env.words()
    a, b = transcript.cut_range(ws, idx)
    env.post("/api/clipboard/copy", start=a, end=b,
             track_ids=[t.id for t in env.p.tracks], group_editing=False)
    return a, b, env.command("cut_words", indices=idx)


def test_x_ripple_cuts_every_track_and_the_words_after_move_up(env):
    before = len(env.clipboard.load().entries())
    a, b, _ = x_cut(env, "on")
    # Pauses 1.5-2.0 and 2.5-3.0: the cut takes the middle of each, 1.75-2.75.
    assert (a, b) == (seconds(1.75), seconds(2.75))
    assert env.p.length == SECONDS * RATE - (b - a)
    for t in env.p.tracks:
        assert sum(c.length for c in t.clips) == SECONDS * RATE - (b - a)
    left = [w["w"] for w in env.words()]
    assert "on" not in left
    assert len(left) == 12
    assert near(env.word("jakso")["s"], seconds(3.0) - (b - a))
    assert near(env.word("kiitos")["s"], seconds(5.5) - (b - a))
    assert not any(w["muted"] for w in env.words())
    # X puts the stretch on the clipboard (copy is one entry, undo-independent).
    assert len(env.clipboard.load().entries()) == before + 1


def test_x_across_speakers_cuts_the_whole_stretch_once(env):
    a, b, _ = x_cut(env, "neljä", "Moi")  # the crosstalk pair, two tracks
    assert (a, b) == (seconds(3.75), seconds(5.1))
    assert env.p.length == SECONDS * RATE - (b - a)
    lengths = {t.name: sum(c.length for c in t.clips) for t in env.p.tracks}
    assert lengths == dict.fromkeys(SPEAKERS, SECONDS * RATE - (b - a))
    assert [w["w"] for w in env.words()
            if w["w"] in {"neljä", "Moi"}] == []
    assert near(env.word("kiitos")["s"], seconds(5.5) - (b - a))


def soft_span(words, idx, track):
    """The Backspace stretch on one track (ui/transcript-model.js deleteSpan)."""
    mine = [i for i in idx if words[i]["track"] == track]
    first = min(words[i]["s"] for i in mine)
    last = max(words[i]["e"] for i in mine)
    before = [w["e"] for w in words if w["track"] == track and w["e"] <= first]
    after = [w["s"] for w in words if w["track"] == track and w["s"] >= last]
    return ((max(before) + first) // 2 if before else first,
            (last + min(after)) // 2 if after else last)


def backspace(env: Env, *texts: str):
    ws = env.words()
    idx = env.index(*texts)
    for track in dict.fromkeys(ws[i]["track"] for i in idx):
        a, b = soft_span(ws, idx, track)
        env.edit("mute_range", start=a, end=b, track_ids=[track], group_editing=False)


def test_backspace_soft_deletes_on_this_speaker_only_and_keeps_the_gap(env):
    entries = len(env.clipboard.load().entries())
    length = env.p.length
    others = {n: env.track(n).clips for n in ("Olli", "Panu")}
    kiitos = env.word("kiitos")
    backspace(env, "kiitos")
    assert env.p.length == length  # nothing moved
    assert len(env.clipboard.load().entries()) == entries  # Backspace never copies
    assert {n: env.track(n).clips for n in ("Olli", "Panu")} == others
    kari = env.track("Kari").clips
    assert [c.muted for c in kari] == [False, True, False]
    assert kari[0].end == kari[1].start
    assert kari[1].end == kari[2].start
    assert kari[2].end == SECONDS * RATE
    ws = {w["w"]: w for w in env.words()}
    assert ws["kiitos"]["muted"] is True
    assert (ws["kiitos"]["s"], ws["kiitos"]["e"]) == (kiitos["s"], kiitos["e"])
    assert [w for w, v in ws.items() if v["muted"]] == ["kiitos"]
    assert near(ws["vastaus"]["s"], seconds(7.5))  # later words did not move


def test_backspace_on_a_crosstalk_selection_mutes_each_speakers_own_track(env):
    backspace(env, "neljä", "Moi")
    muted = {w["w"] for w in env.words() if w["muted"]}
    assert muted == {"neljä", "Moi"}
    assert [c.muted for c in env.track("Panu").clips] == [False]
    assert any(c.muted for c in env.track("Olli").clips)
    assert any(c.muted for c in env.track("Kari").clips)


def test_soft_delete_is_restorable_and_rejoins_the_clips(env):
    backspace(env, "kiitos")
    muted = [c.id for c in env.track("Kari").clips if c.muted]
    env.edit("restore_cuts", clip_ids=muted)
    assert [(c.start, c.offset, c.length, c.muted) for c in env.track("Kari").clips] == [
        (0, 0, SECONDS * RATE, False)]
    assert not any(w["muted"] for w in env.words())
    assert json.loads(env.snapshot())["tracks"][1]["clips"][0]["length"] == SECONDS * RATE


def test_undo_redo_of_x_and_backspace_restores_equal_state(env):
    s0 = env.snapshot()
    x_cut(env, "on")
    s1 = env.snapshot()
    backspace(env, "kiitos")
    s2 = env.snapshot()
    env.undo()
    assert env.snapshot() == s1
    env.undo()
    assert env.snapshot() == s0
    env.redo()
    env.redo()
    assert env.snapshot() == s2


def test_cut_words_rejects_bad_indices_and_changes_nothing(env):
    s0 = env.snapshot()
    for bad in ([], [99], [-1]):
        r = env.client.post("/api/command", json={"name": "cut_words",
                                                  "args": {"indices": bad}})
        assert r.status_code == 400, r.text
    assert env.snapshot() == s0


# -- 3. clip edits ---------------------------------------------------------------


def edit_roundtrip(env: Env, op: str, **args):
    """Apply the edit, check it changed the state, undo, check equality, redo."""
    before = env.snapshot()
    env.edit(op, **args)
    after = env.snapshot()
    assert after != before, op
    env.undo()
    assert env.snapshot() == before, f"undo of {op}"
    env.redo()
    assert env.snapshot() == after, f"redo of {op}"


def test_split_trim_move_undo_redo(env):
    clip = clips_of(env, "Olli")[0]
    edit_roundtrip(env, "split_clip", clip_id=clip.id, at=seconds(6))
    left, right = clips_of(env, "Olli")
    assert (left.end, right.start, right.offset) == (seconds(6),) * 3
    assert left.media == right.media
    # words are split between the halves by midpoint, none lost or doubled
    assert [w["w"] for w in env.words() if w["spk"] == "Olli"] == [
        w for w, _, _ in SPEAKERS["Olli"][1]]

    edit_roundtrip(env, "trim_clip", clip_id=right.id, start=seconds(7))
    right = clips_of(env, "Olli")[1]
    assert (right.start, right.offset) == (seconds(7), seconds(7))
    assert right.end == SECONDS * RATE

    edit_roundtrip(env, "trim_clip", clip_id=right.id, end=seconds(10))
    assert clips_of(env, "Olli")[1].end == seconds(10)

    edit_roundtrip(env, "move_clip", clip_id=right.id, start=seconds(8))
    moved = clips_of(env, "Olli")[1]
    assert (moved.start, moved.offset) == (seconds(8), seconds(7))


def test_trim_moves_only_the_edge_and_hides_the_words_outside(env):
    clip = clips_of(env, "Panu")[0]
    env.edit("trim_clip", clip_id=clip.id, start=seconds(9))
    assert "No" not in [w["w"] for w in env.words()]
    assert near(env.word("juu")["s"], seconds(9.5))  # the rest did not slide
    env.undo()
    assert "No" in [w["w"] for w in env.words()]


def test_ripple_cut_range_closes_the_gap_on_the_chosen_tracks_only(env):
    # Shift+X / "this speaker only" ripple: one track gets shorter, others not.
    kari = env.track("Kari").id
    edit_roundtrip(env, "cut_range", start=seconds(2), end=seconds(3), track_ids=[kari],
                   group_editing=False)
    assert sum(c.length for c in clips_of(env, "Kari")) == SECONDS * RATE - RATE
    assert sum(c.length for c in clips_of(env, "Olli")) == SECONDS * RATE
    assert env.p.length == SECONDS * RATE  # the longest track decides


def test_lift_cut_to_clipboard_then_paste_insert(env):
    olli = env.track("Olli").id
    s0 = env.snapshot()
    out = env.edit("clipboard_cut", start=seconds(2), end=seconds(3), track_ids=[olli],
                   group_editing=False)
    assert out["clipboard"]["ok"] is True
    entry = out["clipboard"]["entry"]
    assert sum(c.length for c in clips_of(env, "Olli")) == (SECONDS - 1) * RATE
    s1 = env.snapshot()
    # paste it back where it came from: insert ripples Olli (and only Olli)
    env.edit("clipboard_paste", entry_id=entry, at=seconds(2), mode="insert",
             group_editing=False)
    assert sum(c.length for c in clips_of(env, "Olli")) == SECONDS * RATE
    assert sum(c.length for c in clips_of(env, "Kari")) == SECONDS * RATE
    # the audio is back in place: Olli's pasted stretch plays recording 2-3 s
    pasted = [c for c in clips_of(env, "Olli") if c.start == seconds(2)]
    assert pasted
    assert pasted[0].offset == seconds(2)
    env.undo()
    assert env.snapshot() == s1
    env.undo()
    assert env.snapshot() == s0


def test_paste_insert_at_a_later_point_shifts_the_rest(env):
    kari, olli = env.track("Kari").id, env.track("Olli").id
    out = env.edit("clipboard_cut", start=seconds(1), end=seconds(2), track_ids=[olli],
                   group_editing=False)
    entry = out["clipboard"]["entry"]
    env.edit("clipboard_paste", entry_id=entry, at=seconds(6), mode="insert",
             group_editing=False)
    olli_clips = clips_of(env, "Olli")
    assert sum(c.length for c in olli_clips) == SECONDS * RATE
    assert any(c.start == seconds(6) and c.offset == seconds(1) for c in olli_clips)
    assert sum(c.length for c in clips_of(env, "Kari")) == SECONDS * RATE
    assert kari  # untouched track keeps its single clip
    assert len(clips_of(env, "Kari")) == 1


# -- 4. mute, solo, bus ----------------------------------------------------------


def muted_words(env: Env) -> set[str]:
    return {w["w"] for w in env.words() if w["muted"]}


def names(env: Env, ids) -> set[str]:
    return {t.name for t in env.p.tracks if t.id in ids}


def test_track_mute_solo_and_bus_mute_drive_the_muted_words(env):
    olli, kari, panu = (env.track(n).id for n in ("Olli", "Kari", "Panu"))
    s0 = env.snapshot()

    env.edit("set_track", track_id=kari, mute=True)
    assert names(env, transcript.silent_tracks(env.p)) == {"Kari"}
    assert muted_words(env) == {w for w, _, _ in SPEAKERS["Kari"][1]}

    env.edit("solo", track_id=olli)  # solo overrides mute: only Olli plays
    assert names(env, transcript.silent_tracks(env.p)) == {"Kari", "Panu"}
    assert muted_words(env) == ({w for w, _, _ in SPEAKERS["Kari"][1]}
                                | {w for w, _, _ in SPEAKERS["Panu"][1]})

    env.edit("solo", track_id=kari)  # exclusive: Kari alone, though muted, plays
    assert names(env, transcript.silent_tracks(env.p)) == {"Olli", "Panu"}
    env.edit("solo", track_id=kari)  # same again clears solo
    assert names(env, transcript.silent_tracks(env.p)) == {"Kari"}

    env.edit("set_track", track_id=kari, mute=False)
    env.edit("add_bus", bus_id="b1", name="Guests", track_ids=[kari, panu])
    assert muted_words(env) == set()
    env.edit("set_bus", bus_id="b1", mute=True)
    assert names(env, transcript.silent_tracks(env.p)) == {"Kari", "Panu"}
    assert "kiitos" in muted_words(env)
    assert "Hei" not in muted_words(env)

    env.edit("set_bus", bus_id="b1", mute=False)
    assert muted_words(env) == set()
    for _ in range(6):
        env.undo()
    assert env.snapshot() == s0


def test_a_muted_stretch_marks_only_the_words_under_it(env):
    kari = env.track("Kari").id
    env.edit("mute_ranges", track_id=kari, ranges=[[seconds(6.3), seconds(7.2)]])
    assert muted_words(env) == {"kysymys"}
    # a word that straddles the edge is owned by the side with its midpoint
    env.edit("mute_ranges", track_id=kari, ranges=[[seconds(7.7), seconds(8.2)]])
    assert muted_words(env) == {"kysymys", "vastaus"}


# -- 5. save, close, reopen -------------------------------------------------------


def busy(env: Env):
    """Some of everything: a ripple cut, a soft delete, a bus, mute, a trim."""
    x_cut(env, "on")
    backspace(env, "kiitos")
    kari, panu = env.track("Kari").id, env.track("Panu").id
    env.edit("add_bus", bus_id="b1", name="Guests", track_ids=[kari, panu])
    env.edit("set_bus", bus_id="b1", mute=True)
    env.edit("set_track", track_id=env.track("Olli").id, gain_db=-3.0)
    env.edit("trim_clip", clip_id=env.track("Panu").clips[-1].id, end=seconds(10))


def test_save_close_reopen_is_identical_and_undo_still_works(env, make):
    busy(env)
    state = env.snapshot()
    words = json.dumps(env.words(), sort_keys=True)
    backup = env.session.package.backup()
    assert backup.exists()
    assert backup.stat().st_size > 0
    can_undo_steps = len(env.session.history.nodes())
    env.session.close()

    again = make()
    assert not again.session.read_only
    assert again.snapshot() == state
    assert json.dumps(again.words(), sort_keys=True) == words
    assert len(again.session.history.nodes()) >= can_undo_steps
    again.undo()  # history survived: one step back changes the state
    assert again.snapshot() != state
    again.redo()
    assert again.snapshot() == state


def test_the_backup_restores_to_the_same_project(env, tmp_path, make):
    busy(env)
    state = env.snapshot()
    backup = env.session.package.backup()
    restored = tmp_path / "Restored.kuulas"
    shutil.copytree(env.folder, restored, ignore=shutil.ignore_patterns(
        "project.sqlite*", "lock.json", "locks", "backups"))
    shutil.copy(backup, restored / "project.sqlite")
    again = make(restored)
    assert not again.session.read_only
    assert again.snapshot() == state


def test_a_second_session_on_the_same_folder_is_read_only_with_a_clear_error(env, make):
    x_cut(env, "on")
    state = env.snapshot()
    # Another kuulas window is another process: a live lock of one on this machine.
    (own,) = (env.folder / "locks").glob("*.json")
    lock = json.loads(own.read_text())
    (env.folder / "locks" / "other-window.json").write_text(json.dumps({
        **lock, "instance": "other", "host": socket.gethostname(), "pid": os.getppid()}))
    second = make()
    assert second.session.read_only
    assert second.snapshot() == state  # it can read
    with pytest.raises(KuulasError) as e:
        second.session.edit("set_track", {"track_id": second.track("Olli").id,
                                          "gain_db": -1.0})
    assert e.value.key == "error.history.read_only"
    r = second.client.post("/api/edit", json={"op": "set_track", "args": {
        "track_id": second.track("Olli").id, "gain_db": -1.0}})
    assert r.status_code >= 400
    assert r.json()["error"]["key"] == "error.history.read_only"
    assert r.json()["error"]["text"]  # a sentence, not a stack trace
    r = second.client.post("/api/command", json={"name": "cut_words",
                                                 "args": {"indices": [0]}})
    assert r.status_code >= 400
    assert second.snapshot() == state
    assert env.snapshot() == state  # and the owner is not disturbed


# -- 6. export ---------------------------------------------------------------------


def export(env: Env, tmp_path: Path, kind: str, name: str):
    r = env.post("/api/export", folder=str(tmp_path / name), format="wav", bit_depth=32,
                 kind=kind, processing="dry")
    return r["export"]


def stems(result) -> dict[str, np.ndarray]:
    return {Path(p).stem.split(" \N{EN DASH} ")[1]: wav(p) for p in result["paths"]}


def level(x: np.ndarray, a: float, b: float) -> float:
    return rms(x[seconds(a):seconds(b)])


def test_export_tracks_applies_ripple_and_soft_cuts_with_equal_lengths(env, tmp_path):
    a, b, _ = x_cut(env, "on")  # 1.75-2.75 gone from all tracks
    removed = b - a
    backspace(env, "kiitos")  # Kari silent 5.25-6.25 original -> 4.25..5.25 now
    ks, ke = soft_span(env.words(), env.index("vastaus"), env.track("Kari").id)
    del ks, ke
    muted_clip = next(c for c in env.track("Kari").clips if c.muted)
    result = export(env, tmp_path, "tracks", "stems")

    files = stems(result)
    assert set(files) == {"Olli", "Kari", "Panu"}
    assert len(result["paths"]) == 3
    total = SECONDS * RATE - removed
    assert {len(x) for x in files.values()} == {total}
    assert env.p.length == total

    tone = 0.3 / math.sqrt(2)
    # Olli: untouched but for the ripple; sound everywhere
    assert level(files["Olli"], 0.2, 1.5) == pytest.approx(tone, rel=0.05)
    assert level(files["Olli"], 2.0, 9.0) == pytest.approx(tone, rel=0.05)
    # The ripple-cut stretch is absent: Olli's samples after the cut continue the
    # sine from the far side of the cut (3.0 s of the recording lands at 2.0 s).
    t = np.arange(SECONDS * RATE) / RATE
    original = (0.3 * np.sin(2 * math.pi * 220 * t)).astype(np.float32)
    got = files["Olli"][seconds(2.1):seconds(2.2)]
    assert np.allclose(got, original[seconds(2.1) + removed:seconds(2.2) + removed],
                       atol=2e-3)
    # Kari: silent exactly over the soft-cut stretch, sound either side
    assert level(files["Kari"], muted_clip.start / RATE + 0.05,
                 muted_clip.end / RATE - 0.05) == 0.0
    assert level(files["Kari"], muted_clip.start / RATE - 0.5,
                 muted_clip.start / RATE - 0.1) == pytest.approx(tone, rel=0.05)
    assert level(files["Kari"], muted_clip.end / RATE + 0.1,
                 muted_clip.end / RATE + 0.5) == pytest.approx(tone, rel=0.05)
    # Panu keeps its tone to the end of the shortened edit
    assert level(files["Panu"], 0.5, total / RATE - 0.1) == pytest.approx(tone, rel=0.05)


def test_export_mix_length_is_the_longest_track_and_follows_the_edits(env, tmp_path):
    a, b, _ = x_cut(env, "on")
    backspace(env, "kiitos")
    env.edit("trim_clip", clip_id=env.track("Olli").clips[-1].id, end=seconds(8))
    env.edit("trim_clip", clip_id=env.track("Kari").clips[-1].id, end=seconds(7))
    longest = max(t.clips[-1].end for t in env.p.tracks if t.clips)
    assert longest == env.p.length == SECONDS * RATE - (b - a)  # Panu is longest

    result = export(env, tmp_path, "mix", "mix")
    mix, rate = sf.read(result["path"], dtype="float32", always_2d=True)
    assert rate == RATE
    assert mix.shape[0] == longest
    mono = mix.mean(axis=1)
    # Kari's soft-cut stretch plays no Kari tone: only Olli (until 8 s) and Panu remain.
    k = next(c for c in env.track("Kari").clips if c.muted)
    spec = np.abs(np.fft.rfft(mono[k.start + 4800:k.end - 4800]))
    freqs = np.fft.rfftfreq(k.end - k.start - 9600, 1 / RATE)

    def peak(hz):
        return spec[np.argmin(np.abs(freqs - hz))]

    assert peak(220) > 20 * peak(330)  # Olli is there, Kari is not
    assert peak(440) > 20 * peak(330)
    # After Kari's last clip (7 s) and Olli's (8 s) only Panu remains
    tail = np.abs(np.fft.rfft(mono[seconds(9):seconds(10)]))
    f2 = np.fft.rfftfreq(RATE, 1 / RATE)
    assert tail[np.argmin(np.abs(f2 - 440))] > 20 * tail[np.argmin(np.abs(f2 - 220))]


def test_export_respects_mute_solo_and_bus_in_the_mix_and_the_stems(env, tmp_path):
    kari, panu = env.track("Kari").id, env.track("Panu").id
    env.edit("add_bus", bus_id="b1", name="Guests", track_ids=[kari, panu])
    env.edit("set_bus", bus_id="b1", mute=True)
    result = export(env, tmp_path, "mix", "bus")
    mono = wav(result["path"])
    assert len(mono) == SECONDS * RATE
    spec = np.abs(np.fft.rfft(mono[RATE:2 * RATE]))
    f = np.fft.rfftfreq(RATE, 1 / RATE)
    peak = lambda hz: spec[np.argmin(np.abs(f - hz))]  # noqa: E731
    assert peak(220) > 50 * max(peak(330), peak(440))
    stem = export(env, tmp_path, "tracks", "bus-stems")
    files = stems(stem)
    assert level(files["Kari"], 1, 10) == 0.0
    assert level(files["Panu"], 1, 10) == 0.0
    assert level(files["Olli"], 1, 10) > 0.1
    assert {len(x) for x in files.values()} == {SECONDS * RATE}
