"""Track.mono: a speech track that is mixed down to one channel everywhere."""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import import_plan, messages, mixer, ops
from kuulas.import_plan import ImportItem, plan_import
from kuulas.loudness import measure_clip
from kuulas.model import Media, Project, Track
from kuulas.server import create_app
from kuulas.session import Session

RATE = 1000
HZ = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


class MemoryStore:
    def __init__(self, arrays):
        self.arrays = arrays

    def read(self, media_id, first, count):
        a = self.arrays[media_id]
        out = np.zeros((a.shape[0], count), dtype=np.float32)
        piece = a[:, max(0, first):first + count]
        out[:, : piece.shape[1]] = piece
        return out


def stereo_project(left=1.0, right=1.0, mono=False):
    frames = 2 * RATE
    data = np.stack([np.full(frames, v, np.float32) for v in (left, right)])
    store = MemoryStore({"m": data})
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m", name="m.wav", channels=2, frames=frames))
    p = ops.add_track(p, track_id="t", name="T")
    p = ops.add_clip(p, track_id="t", media_id="m", clip_id="c")
    if mono:
        p = ops.set_track(p, "t", mono=True)
    return p, store


# -- model and ops ---------------------------------------------------------------


def test_mono_false_keeps_the_bytes_of_old_projects():
    assert "mono" not in Track(id="t", name="A").to_dict()


def test_mono_round_trips():
    d = Track(id="t", name="A", mono=True).to_dict()
    assert d["mono"] is True
    assert Track.from_dict(d).mono is True


def test_old_track_dict_reads_as_stereo():
    assert Track.from_dict({"id": "t", "name": "A"}).mono is False


def test_set_track_mono_is_an_edit_and_undoes(tmp_path):
    p = ops.add_track(Project(), track_id="t", name="A")
    assert ops.set_track(p, "t", mono=True).track("t").mono is True
    s = Session(tmp_path / "T.kuulas")
    try:
        s.edit("add_track", {"track_id": "t", "name": "A"})
        s.edit("set_track", {"track_id": "t", "mono": True})
        assert s.state.track("t").mono is True
        s.undo()
        assert s.state.track("t").mono is False
    finally:
        s.close()


# -- mixer -----------------------------------------------------------------------


def test_mono_track_sums_a_centred_voice_without_a_level_change():
    p, store = stereo_project(1.0, 1.0, mono=True)
    out = mixer.mix(p, store, 0, 4)
    np.testing.assert_allclose(out[:, 0], [np.sqrt(0.5)] * 2, rtol=1e-6)


def test_mono_track_is_the_mean_of_left_and_right():
    p, store = stereo_project(1.0, 0.0, mono=True)
    out = mixer.mix(p, store, 0, 4)
    np.testing.assert_allclose(out[:, 0], [0.5 * np.sqrt(0.5)] * 2, rtol=1e-6)


def test_stereo_track_still_keeps_its_sides():
    p, store = stereo_project(1.0, 0.0)
    out = mixer.mix(p, store, 0, 4)
    assert out[0, 0] == pytest.approx(1.0)
    assert out[1, 0] == pytest.approx(0.0)


def test_mono_track_is_panned_like_any_mono_track():
    p, store = stereo_project(1.0, 0.0, mono=True)
    p = ops.set_clip(p, "c", pan=-1.0)
    out = mixer.mix(p, store, 0, 4)
    assert out[0, 0] == pytest.approx(0.5)
    assert out[1, 0] == pytest.approx(0.0, abs=1e-7)


def test_mono_stem_is_one_channel_with_the_mean():
    p, store = stereo_project(1.0, 0.0, mono=True)
    stem = mixer.track_stem(p.track("t"), store, 0, 4, 1, as_heard=False, rate=RATE)
    assert stem.shape == (1, 4)
    np.testing.assert_allclose(stem[0], 0.5)


# -- stems export ---------------------------------------------------------------


def two_channel_wav(path, seconds=1):
    n = seconds * HZ
    rng = np.random.default_rng(3)
    sf.write(path, (rng.standard_normal((n, 2)) * 0.1).astype(np.float32), HZ,
             subtype="PCM_16")
    return path


def export_stems(session, out):
    return session.export({"folder": str(out), "format": "wav", "bit_depth": 32,
                           "kind": "tracks"})


def test_stems_export_writes_a_mono_track_as_one_channel(tmp_path):
    s = Session(tmp_path / "T.kuulas")
    try:
        src = two_channel_wav(tmp_path / "voice.wav")
        s.import_media([str(src)])
        track = s.state.tracks[0]
        s.edit("set_track", {"track_id": track.id, "mono": False})
        (stereo_path,) = export_stems(s, tmp_path / "a")["paths"]
        assert sf.info(stereo_path).channels == 2
        s.edit("set_track", {"track_id": track.id, "mono": True})
        (path,) = export_stems(s, tmp_path / "b")["paths"]
        assert sf.info(path).channels == 1
        got, _ = sf.read(path, dtype="float32", always_2d=True)
        want, _ = sf.read(src, dtype="float32", always_2d=True)
        # Edit fades only touch the ends; the middle is exactly (L+R)/2.
        mid = slice(HZ // 4, -HZ // 4)
        np.testing.assert_allclose(got[mid, 0], want[mid].mean(axis=1), atol=2e-4)
    finally:
        s.close()


# -- loudness -------------------------------------------------------------------


def test_measuring_a_mono_track_measures_the_mean(tmp_path):
    s = Session(tmp_path / "T.kuulas")
    try:
        n = 4 * HZ
        t = np.arange(n) / HZ
        tone = np.sin(2 * np.pi * 1000 * t).astype(np.float32) * 0.1
        sf.write(tmp_path / "v.wav", np.stack([tone, -tone], axis=1), HZ, subtype="FLOAT")
        s.import_media([str(tmp_path / "v.wav")])
        clip = s.state.tracks[0].clips[0]
        assert measure_clip(s.store, clip, HZ) is not None
        # Opposite sides cancel in the mean: silence.
        assert measure_clip(s.store, clip, HZ, mono=True) is None
    finally:
        s.close()


# -- import ---------------------------------------------------------------------


def test_mono_source_makes_a_mono_speech_track():
    (pl,) = plan_import([ImportItem("a.wav", HZ, 1)], HZ)
    assert pl.mono is True


def test_stereo_source_makes_a_stereo_speech_track():
    (pl,) = plan_import([ImportItem("a.wav", HZ, 2)], HZ)
    assert (pl.kind, pl.mono) == ("speech", False)


def test_music_is_never_flagged_mono():
    (pl,) = plan_import([ImportItem("music.wav", HZ, 1)], HZ)
    assert pl.mono is False


def test_the_question_names_only_stereo_speech_tracks():
    plan = plan_import([ImportItem("a.wav", HZ, 1), ImportItem("b.wav", HZ, 2),
                        ImportItem("music.wav", HZ, 2)], HZ)
    assert [(pl.track_key, pl.track_name) for pl in import_plan.stereo_speech(plan)] \
        == [("t1", "b")]


def test_session_import_reports_the_stereo_tracks_and_makes_mono_ones_mono(tmp_path):
    s = Session(tmp_path / "T.kuulas")
    try:
        sf.write(tmp_path / "one.wav", np.zeros(HZ, np.float32), HZ, subtype="FLOAT")
        two_channel_wav(tmp_path / "two.wav")
        s.import_media([str(tmp_path / "one.wav"), str(tmp_path / "two.wav")])
        one, two = s.state.tracks
        assert (one.mono, two.mono) == (True, False)
        assert s.last_import_stereo == [{"id": two.id, "name": "two"}]
        s.import_media([str(tmp_path / "one.wav")])
        assert s.last_import_stereo == []
    finally:
        s.close()


def test_the_import_answer_lists_the_stereo_tracks(tmp_path):

    class Engine:
        def status(self):
            return {"playing": False, "position": 0, "until": None, "notices": []}

        def close(self):
            pass

    s = Session(tmp_path / "T.kuulas")
    try:
        ui = tmp_path / "ui"
        ui.mkdir()
        two_channel_wav(tmp_path / "duo.wav")
        client = TestClient(create_app(s, Engine(), language="en", ui_dir=ui))
        body = {"paths": [str(tmp_path / "duo.wav")]}
        answer = client.post("/api/import", json=body).json()
        assert [x["name"] for x in answer["stereo"]] == ["duo"]
    finally:
        s.close()
