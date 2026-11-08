"""Used-only linked-media consolidation (WP20)."""

import numpy as np
import pytest
import soundfile as sf

from kuulas import ops
from kuulas.history import History
from kuulas.session import Session

RATE = 48_000


@pytest.fixture
def session(tmp_path):
    project = Session(tmp_path / "Talk.kuulas")
    yield project
    project.close()


def source_wav(path, seconds=10, amplitude=0.25):
    audio = np.full((seconds * RATE, 1), amplitude, dtype=np.float32)
    sf.write(path, audio, RATE, subtype="PCM_16")
    return audio


def import_source(session, path):
    session.import_media([str(path)])
    media = next(media for media in session.state.media if media.name == path.name)
    for track in session.state.tracks:
        for clip in track.clips:
            if clip.media == media.id:
                session.edit("delete_clip", {"clip_id": clip.id})
    return media


def add_used_clip(session, media_id):
    session.edit("add_track", {"track_id": "voice", "name": "Voice"})
    session.edit("add_clip", {
        "track_id": "voice",
        "clip_id": "clip",
        "media_id": media_id,
        "start": 6 * RATE,
        "offset": 4 * RATE,
        "length": RATE,
    })


def test_consolidate_plan_reports_used_ranges_and_estimated_savings(session, tmp_path):
    source = tmp_path / "voice.wav"
    source_wav(source)
    media = session.store.import_file(source)
    add_used_clip(session, media.id)

    plan = session.consolidate_plan()

    row = next(item for item in plan["media"] if item["id"] == media.id)
    assert row["ranges"] == [[2 * RATE, 7 * RATE]]
    assert row["source_bytes"] == source.stat().st_size
    assert row["estimated_bytes"] == round(source.stat().st_size * 0.5)
    assert row["estimated_savings_bytes"] == row["source_bytes"] - row["estimated_bytes"]
    assert plan["handle_seconds"] == 2.0
    assert plan["estimated_savings_bytes"] == row["estimated_savings_bytes"]


def test_consolidate_plan_matches_history_aware_ranges_written_by_command(
    session, tmp_path,
):
    source = tmp_path / "voice.wav"
    want = source_wav(source)
    session.import_media([str(source)])
    clip = session.state.tracks[0].clips[0]
    media_id = clip.media
    session.edit("trim_clip", {"clip_id": clip.id, "start": 5 * RATE})

    plan = session.consolidate_plan()
    row = next(item for item in plan["media"] if item["id"] == media_id)
    session.command("consolidate", {"used_only": True})

    assert row["ranges"] == [[0, len(want)]]
    assert row["estimated_bytes"] == row["source_bytes"]
    assert row["estimated_savings_bytes"] == 0
    assert session.store.partial_info(media_id)["ranges"] == row["ranges"]


def test_used_only_consolidation_preserves_timeline_audio_and_full_source_relink(
    session, tmp_path,
):
    source = tmp_path / "voice.wav"
    want = source_wav(source)
    media = session.store.import_file(source)
    add_used_clip(session, media.id)
    state = session.state
    history = session.history.nodes()

    session.command("consolidate", {"used_only": True})

    assert session.state.tracks == state.tracks
    assert session.history.nodes() == history
    assert not session.store.is_linked(media.id)
    info = session.store.partial_info(media.id)
    assert info["ranges"] == [[2 * RATE, 7 * RATE]]
    got = session.store.read(media.id, 0, len(want))
    np.testing.assert_array_equal(got[:, :2 * RATE], 0)
    np.testing.assert_allclose(got[:, 2 * RATE:7 * RATE], want[2 * RATE:7 * RATE].T)
    np.testing.assert_array_equal(got[:, 7 * RATE:], 0)

    assert session.store.relink(tmp_path) == {media.id: str(source)}
    assert session.store.partial_info(media.id) is None
    np.testing.assert_allclose(session.store.read(media.id, 0, len(want)), want.T)


def test_used_only_consolidation_leaves_unused_linked_media_alone(session, tmp_path):
    used_path = tmp_path / "used.wav"
    unused_path = tmp_path / "unused.wav"
    source_wav(used_path)
    source_wav(unused_path, amplitude=0.5)
    used = import_source(session, used_path)
    unused = import_source(session, unused_path)
    add_used_clip(session, used.id)

    session.command("consolidate", {"used_only": True})

    assert not session.store.is_linked(used.id)
    assert session.store.is_linked(unused.id)


def test_partial_write_failure_leaves_source_linked_and_removes_temporary_file(
    session, tmp_path, monkeypatch,
):
    source = tmp_path / "voice.wav"
    source_wav(source)
    media = import_source(session, source)
    add_used_clip(session, media.id)
    partial = session.store.working_file(media.id).with_name(
        session.store.working_file(media.id).name + ".partial"
    )

    def fail_read(*_args):
        raise OSError("injected read failure")

    monkeypatch.setattr(session.store, "read", fail_read)
    with pytest.raises(OSError, match="injected read failure"):
        session.command("consolidate", {"used_only": True})

    assert session.store.is_linked(media.id)
    assert session.store.partial_info(media.id) is None
    assert not partial.exists()


def test_used_only_consolidation_keeps_ranges_reachable_by_undo(session, tmp_path):
    source = tmp_path / "voice.wav"
    want = source_wav(source)
    session.import_media([str(source)])
    clip = session.state.tracks[0].clips[0]
    media_id = clip.media
    session.edit("trim_clip", {"clip_id": clip.id, "start": 5 * RATE})

    session.command("consolidate", {"used_only": True})

    assert session.store.partial_info(media_id)["ranges"] == [[0, len(want)]]
    assert session.undo()
    np.testing.assert_allclose(
        session.store.read(media_id, 0, 5 * RATE), want[: 5 * RATE].T, atol=1e-5
    )


def test_used_only_consolidation_keeps_ranges_in_other_edits(session, tmp_path):
    source = tmp_path / "voice.wav"
    want = source_wav(source)
    media = session.store.import_file(source)
    add_used_clip(session, media.id)

    other_id = session.history.create_edit("Other")
    other = History(session.history.path, edit=other_id)
    try:
        clip = next(c for track in other.state.tracks for c in track.clips)
        other.commit("use the start", ops.trim_clip(
            other.state, clip.id, start=2 * RATE, end=3 * RATE
        ))
    finally:
        other.close()

    session.command("consolidate", {"used_only": True})

    assert session.store.partial_info(media.id)["ranges"] == [[0, 7 * RATE]]
    reopened = History(session.history.path, edit=other_id)
    try:
        clip = next(c for track in reopened.state.tracks for c in track.clips)
        np.testing.assert_allclose(
            session.store.read(media.id, clip.offset, clip.length), want[:RATE].T,
            atol=1e-5,
        )
    finally:
        reopened.close()


def test_partial_audio_uses_distinct_persistent_analysis_and_waveform_caches(
    tmp_path,
):
    source = tmp_path / "voice.wav"
    source_wav(source)
    store = Session(tmp_path / "Caches.kuulas")
    try:
        store.import_media([str(source)])
        media = store.state.media[0]
        media_id = media.id
        full_peaks = store.store._peaks_path(media.sha256)
        full_tile, full_etag = store.store.peak_tile(media_id, 256, 0)
        assert full_tile
        full_energy = store.store.envelope(media_id, RATE)
        assert full_energy[0] > 0
        store.store.onsets(media_id)

        store.store.consolidate({media_id: ((5 * RATE, 6 * RATE),)}, 0)
        partial_info = store.store.partial_info(media_id)
        assert partial_info["ranges"] == [[5 * RATE, 6 * RATE]]
        assert full_peaks.exists(), "partial analysis must preserve the full-source cache"

        partial_peaks = store.store._base_peaks(media_id)
        first_used_bin = 5 * RATE // 256
        assert not partial_peaks[:first_used_bin].any()
        assert partial_peaks[first_used_bin].any()
        partial_tile, partial_etag = store.store.peak_tile(media_id, 256, 0)
        assert partial_tile
        assert partial_etag != full_etag
        partial_energy = store.store.envelope(media_id, RATE)
        assert not partial_energy[0]
        assert partial_energy[5] > 0

        reopened = Session(tmp_path / "Caches.kuulas")
        try:
            reopened_peaks = reopened.store._base_peaks(media_id)
            assert not reopened_peaks[:first_used_bin].any()
            assert reopened.store.peak_tile(media_id, 256, 0)[1] == partial_etag
        finally:
            reopened.close()

        assert store.store.relink(tmp_path) == {media_id: str(source)}
        assert full_peaks.exists(), "relink should retain the full-source cache"
        assert store.store.peak_tile(media_id, 256, 0)[1] == full_etag
    finally:
        store.close()

