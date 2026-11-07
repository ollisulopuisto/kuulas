"""Voice-chain output is kept as an alternate source, not a destructive edit."""

from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np
import soundfile as sf
from speechmix import chain

from kuulas import ops
from kuulas import session as session_module
from kuulas.session import Session

RATE = 48_000


def _wait_for_jobs(session, job_ids):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        jobs = {job["id"]: job for job in session.jobs.list()}
        if all(jobs[job_id]["state"] in {"completed", "failed", "cancelled"}
               for job_id in job_ids):
            return [jobs[job_id] for job_id in job_ids]
        time.sleep(0.01)
    raise AssertionError(session.jobs.list())


def test_add_array_stores_a_24_bit_variant_with_lineage(tmp_path):
    session = Session(tmp_path / "Voice.kuulas")
    source_path = tmp_path / "source.wav"
    sf.write(source_path, np.zeros(RATE, dtype=np.float32), RATE, subtype="PCM_16")
    try:
        session.import_media([str(source_path)], copy=True)
        source = session.state.media[0]
        audio = np.full((1, RATE), 0.125, dtype=np.float32)

        variant = session.store.add_array(audio, "source voice chain", source.id)

        assert variant.variant_of == source.id
        assert variant.variant == "voice chain"
        assert variant.frames == source.frames == RATE
        assert session.state.media_item(variant.id).variant_of == source.id
        assert session.state.media_item(variant.id).variant == "voice chain"
        info = sf.info(session.store.working_file(variant.id))
        assert info.format == "FLAC"
        assert info.subtype == "PCM_24"
        assert info.frames == RATE
        np.testing.assert_allclose(session.store.read(variant.id, 0, RATE), audio,
                                   atol=1 / (2 ** 23))
    finally:
        session.close()


def test_use_variant_swaps_only_selected_clips_and_undo_restores_source(tmp_path):
    session = Session(tmp_path / "Voice.kuulas")
    source_path = tmp_path / "source.wav"
    sf.write(source_path, np.zeros(RATE, dtype=np.float32), RATE, subtype="PCM_16")
    try:
        session.import_media([str(source_path)], copy=True)
        source = session.state.media[0]
        track = session.state.tracks[0]
        session.edit("add_clip", {
            "track_id": track.id, "media_id": source.id, "clip_id": "source-clip",
        })
        session.edit("add_clip", {
            "track_id": track.id, "media_id": source.id, "start": RATE,
            "clip_id": "source-clip-2",
        })
        variant = session.store.add_array(
            np.full((1, RATE), 0.125, dtype=np.float32), "voice chain", source.id,
        )

        session.edit("use_variant", {"clip_ids": ["source-clip"],
                                      "media_id": variant.id})

        clips = {clip.id: clip for clip in session.state.track(track.id).clips}
        assert clips["source-clip"].media == variant.id
        assert clips["source-clip-2"].media == source.id
        assert session.undo() is not None
        clips = {clip.id: clip for clip in session.state.track(track.id).clips}
        assert clips["source-clip"].media == source.id
        assert clips["source-clip-2"].media == source.id
    finally:
        session.close()


def test_use_variant_rejects_unrelated_media():
    project = ops.Project(
        rate=RATE,
        media=(
            ops.Media(id="source", name="source", channels=1, frames=10),
            ops.Media(id="variant", name="variant", channels=1, frames=10,
                      variant_of="source", variant="voice chain"),
            ops.Media(id="other", name="other", channels=1, frames=10),
        ),
        tracks=(ops.Track(id="track", name="Voice", clips=(
            ops.Clip(id="clip", media="other", start=0, offset=0, length=10),
        )),),
    )
    try:
        ops.use_variant(project, ["clip"], "variant")
    except ops.EditError:
        pass
    else:
        raise AssertionError("a clip outside the variant pair must be refused")


def test_process_voice_stores_one_variant_and_undo_restores_clips(
    tmp_path, monkeypatch,
):
    session = Session(tmp_path / "Voice.kuulas")
    source_path = tmp_path / "voice.wav"
    sf.write(source_path, np.full(RATE, 0.05, dtype=np.float32), RATE,
             subtype="PCM_16")
    try:
        session.import_media([str(source_path)], copy=True)
        source = session.state.media[0]
        track = session.state.tracks[0]
        original_ids = {clip.id for clip in track.clips if clip.media == source.id}
        assert original_ids

        def fake_lanes(project, store):
            track = project.tracks[0]
            return SimpleNamespace(speakers=[SimpleNamespace(
                name=track.speaker or track.name, on=np.ones(20, dtype=bool),
            )])

        calls = []

        def fake_process(audio, rate, settings, gain_db, speech, target_lufs,
                         plugin=None, stage=None, speaking=None):
            calls.append((audio.shape, rate, settings, gain_db, speech, target_lufs,
                          speaking.copy()))
            return audio + np.float32(0.125), SimpleNamespace(frames=audio.shape[1])

        monkeypatch.setattr(session_module.analysis, "speech_lanes", fake_lanes)
        monkeypatch.setattr(chain, "process", fake_process)
        existing_jobs = {job["id"] for job in session.jobs.list()}
        session.command("process_voice", {"track_ids": [track.id]})
        job_ids = [job["id"] for job in session.jobs.list()
                   if job["id"] not in existing_jobs]
        assert len(job_ids) == 1

        job, = _wait_for_jobs(session, job_ids)
        assert job["state"] == "completed"
        assert len(calls) == 1
        assert calls[0][0] == (source.channels, source.frames)
        assert calls[0][3:6] == (0.0, True, None)
        variants = [media for media in session.state.media
                    if media.variant_of == source.id]
        assert len(variants) == 1
        variant = variants[0]
        assert variant.frames == source.frames
        assert original_ids <= {
            clip.id for clip in session.state.track(track.id).clips
            if clip.media == variant.id
        }
        assert session.undo() is not None
        restored = {clip.id: clip.media for clip in session.state.track(track.id).clips}
        assert all(restored[clip_id] == source.id for clip_id in original_ids)
    finally:
        session.close()


def test_voice_chain_failure_does_not_stop_other_media(tmp_path, monkeypatch):
    session = Session(tmp_path / "Voice.kuulas")
    paths = [tmp_path / "first.wav", tmp_path / "second.wav"]
    for index, path in enumerate(paths, start=1):
        sf.write(path, np.full(RATE, 0.02 * index, dtype=np.float32), RATE,
                 subtype="PCM_16")
    try:
        session.import_media([str(path) for path in paths], copy=True)
        sources = list(session.state.media)
        tracks = session.state.tracks
        clip_ids = {
            media.id: {clip.id for track in tracks for clip in track.clips
                       if clip.media == media.id}
            for media in sources
        }
        original_read = session.store.read

        def read(media_id, first, count):
            if media_id == sources[0].id:
                raise OSError("injected decoder failure")
            return original_read(media_id, first, count)

        monkeypatch.setattr(session.store, "read", read)
        monkeypatch.setattr(
            session_module.analysis,
            "speech_lanes",
            lambda project, _store: SimpleNamespace(speakers=[SimpleNamespace(
                name=project.tracks[0].name, on=np.ones(20, dtype=bool),
            )]),
        )
        monkeypatch.setattr(
            chain, "process",
            lambda audio, *_args, **_kwargs: (audio + 0.125, None),
        )
        existing_jobs = {job["id"] for job in session.jobs.list()}
        session.command("process_voice", {"track_ids": [track.id for track in tracks]})
        job_ids = [job["id"] for job in session.jobs.list()
                   if job["id"] not in existing_jobs]
        results = _wait_for_jobs(session, job_ids)

        assert len(results) == 2
        assert [job["state"] for job in results].count("completed") == 1
        assert [job["state"] for job in results].count("failed") == 1
        variants = [media for media in session.state.media
                    if media.variant_of is not None]
        assert len(variants) == 1
        clips = {clip.id: clip for track in session.state.tracks for clip in track.clips}
        assert all(clips[clip_id].media == sources[0].id
                   for clip_id in clip_ids[sources[0].id])
        assert all(clips[clip_id].media == variants[0].id
                   for clip_id in clip_ids[sources[1].id])
    finally:
        session.close()
