"""Used-only linked-media consolidation (WP20)."""

import numpy as np
import pytest
import soundfile as sf

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
    media = import_source(session, source)
    add_used_clip(session, media.id)

    plan = session.consolidate_plan()

    row = next(item for item in plan["media"] if item["id"] == media.id)
    assert row["ranges"] == [[2 * RATE, 7 * RATE]]
    assert row["source_bytes"] == source.stat().st_size
    assert row["estimated_bytes"] == round(source.stat().st_size * 0.5)
    assert row["estimated_savings_bytes"] == row["source_bytes"] - row["estimated_bytes"]
    assert plan["handle_seconds"] == 2.0
    assert plan["estimated_savings_bytes"] == row["estimated_savings_bytes"]


def test_used_only_consolidation_preserves_timeline_audio_and_full_source_relink(
    session, tmp_path,
):
    source = tmp_path / "voice.wav"
    want = source_wav(source)
    media = import_source(session, source)
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

