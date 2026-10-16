import os
import struct
import subprocess

import numpy as np
import pytest
import soundfile as sf
from pedalboard.io import AudioFile

from kuulas import media as media_module
from kuulas.clock import FLICKS
from kuulas.media import MediaError, MediaStore


def write_wav(path, audio, rate):
    with AudioFile(str(path), "w", samplerate=rate, num_channels=audio.shape[0]) as f:
        f.write(audio)


def test_import_decodes_to_the_project_rate(tmp_path):
    src = tmp_path / "in.wav"
    write_wav(src, np.full((1, 44100), 0.5, dtype=np.float32), 44100)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src)
    assert media.channels == 1
    assert abs(media.frames - 48000) <= 1
    piece = store.read(media.id, 1000, 10)
    np.testing.assert_allclose(piece, 0.5, atol=1e-3)


def test_reads_past_the_end_are_zero_padded(tmp_path):
    src = tmp_path / "in.wav"
    write_wav(src, np.ones((2, 480), dtype=np.float32), 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src)
    piece = store.read(media.id, 470, 20)
    assert piece.shape == (2, 20)
    assert piece[:, :10].all()
    assert not piece[:, 10:].any()
    assert not store.read(media.id, -5, 5).any()


def test_same_file_imports_once(tmp_path):
    src = tmp_path / "in.wav"
    write_wav(src, np.ones((1, 480), dtype=np.float32), 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    assert store.import_file(src).id == store.import_file(src).id


def test_peaks_summarise_min_and_max(tmp_path):
    src = tmp_path / "in.wav"
    audio = np.zeros((1, 4800), dtype=np.float32)
    audio[0, 100] = 0.9
    audio[0, 200] = -0.7
    write_wav(src, audio, 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src)
    peaks = store.peaks(media.id, per=4800)
    assert peaks.shape == (1, 2)
    assert peaks[0, 0] == np.float32(-0.7) or abs(peaks[0, 0] + 0.7) < 1e-3
    assert abs(peaks[0, 1] - 0.9) < 1e-3


def test_renamed_and_moved_file_is_recognised_by_its_hash(tmp_path):
    src = tmp_path / "anna.wav"
    write_wav(src, np.ones((1, 480), dtype=np.float32), 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    first = store.import_file(src)
    moved = tmp_path / "elsewhere" / "Anna FINAL (2).wav"
    moved.parent.mkdir()
    src.rename(moved)
    again = store.import_file(moved)
    assert again.id == first.id
    assert again.sha256 == first.sha256
    # Every name and place the bytes were seen under is remembered.
    assert {str(src), str(moved)} <= set(store.seen_paths(first.sha256))


def test_find_by_hash_identifies_a_file_without_importing(tmp_path):
    src = tmp_path / "a.wav"
    write_wav(src, np.ones((1, 480), dtype=np.float32), 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src)
    copy = tmp_path / "b.wav"
    copy.write_bytes(src.read_bytes())
    assert store.find(copy) == media.id
    other = tmp_path / "c.wav"
    write_wav(other, np.zeros((1, 480), dtype=np.float32), 48000)
    assert store.find(other) is None


def add_bext(path, time_reference: int):
    """Insert a minimal BWF ``bext`` chunk with the given TimeReference."""
    data = path.read_bytes()
    bext = bytearray(602)
    struct.pack_into("<Q", bext, 338, time_reference)
    chunk = b"bext" + struct.pack("<I", len(bext)) + bytes(bext)
    body = data[12:] + chunk
    path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body)


def test_bwf_time_reference_is_read_on_the_recording_clock(tmp_path):
    src = tmp_path / "rec.wav"
    write_wav(src, np.ones((1, 480), dtype=np.float32), 44100)
    add_bext(src, 44100 * 3600)  # recorded at 01:00:00
    store = MediaStore(tmp_path / "media", rate=48000)
    assert store.import_file(src).time_ref_flicks == 3600 * FLICKS


def test_bwf_time_reference_is_stored_in_flicks(tmp_path):
    # One sample past 01:00:00 at 44.1 kHz is not a whole number of 48 kHz
    # frames; in flicks it is exact, and the row keeps it so.
    src = tmp_path / "rec.wav"
    write_wav(src, np.ones((1, 480), dtype=np.float32), 44100)
    add_bext(src, 44100 * 3600 + 1)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src)
    want = 3600 * FLICKS + FLICKS // 44100
    assert media.time_ref_flicks == want
    row = store.db.execute("select time_ref_flicks from media where id=?",
                           (media.id,)).fetchone()
    assert row == (want,)


def test_files_without_bext_have_no_time_reference(tmp_path):
    src = tmp_path / "plain.wav"
    write_wav(src, np.ones((1, 480), dtype=np.float32), 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    assert store.import_file(src).time_ref_flicks is None


def test_a_source_rate_flicks_cannot_hold_is_refused(tmp_path):
    src = tmp_path / "odd.wav"
    write_wav(src, np.ones((1, 480), dtype=np.float32), 37800)
    store = MediaStore(tmp_path / "media", rate=48000)
    with pytest.raises(MediaError) as err:
        store.import_file(src)
    assert err.value.key == "error.clock.rate"
    assert store.ids() == []


def write_int16(path, audio, rate):
    with AudioFile(str(path), "w", samplerate=rate, num_channels=audio.shape[0],
                   bit_depth=16) as f:
        f.write(audio)


def decoded(path):
    """Reference decode: libsndfile, which maps int16 -32768 to exactly -1.0.

    (pedalboard's reader scales integers by a hair more than 2**15, so
    -32768 comes back as -32769/32768; it is not used as a reference.)
    """
    return sf.read(str(path), dtype="float32", always_2d=True)[0].T


def test_pcm_at_project_rate_is_kept_as_bit_exact_flac_only(tmp_path):
    rng = np.random.default_rng(0)
    audio = (rng.integers(-30000, 30000, (1, 48000)) / 32768).astype(np.float32)
    src = tmp_path / "voice.wav"
    write_int16(src, audio, 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src, copy=True)
    np.testing.assert_array_equal(store.read(media.id, 0, 48000), decoded(src))
    assert store.is_lossless(media.id)
    # No second copy of the original: the FLAC is the original's samples.
    assert not any((tmp_path / "media" / "originals").glob("*"))
    assert store.working_file(media.id).suffix == ".flac"


def test_resampled_source_keeps_its_original_too(tmp_path):
    src = tmp_path / "music.wav"
    write_int16(src, np.zeros((2, 44100), dtype=np.float32), 44100)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src, copy=True)
    assert not store.is_lossless(media.id)
    assert len(list((tmp_path / "media" / "originals").glob("*"))) == 1


def test_flac_storage_is_smaller_than_float(tmp_path):
    t = np.arange(48000 * 5) / 48000
    speechy = (0.3 * np.sin(2 * np.pi * 220 * t) * np.sin(2 * np.pi * 3 * t))
    src = tmp_path / "v.wav"
    write_int16(src, speechy[None].astype(np.float32), 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src, copy=True)
    assert store.working_file(media.id).stat().st_size < speechy.size * 4 / 2


def test_many_files_import_in_parallel(tmp_path):
    paths = []
    for i in range(4):
        src = tmp_path / f"t{i}.wav"
        write_int16(src, np.full((1, 4800), 0.01 * (i + 1), dtype=np.float32), 48000)
        paths.append(src)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_files(paths)
    assert [m.name for m in media] == [p.name for p in paths]
    assert len({m.id for m in media}) == 4


# -- linked media (left in place) ---------------------------------------------


def test_pcm_at_project_rate_is_linked_in_place_without_a_copy(tmp_path):
    src = tmp_path / "voice.wav"
    write_int16(src, np.full((1, 4800), 0.25, dtype=np.float32), 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src)
    assert store.is_linked(media.id)
    assert not store.working_file(media.id).exists()
    np.testing.assert_array_equal(store.read(media.id, 0, 4800), decoded(src))


def test_moved_linked_file_is_found_again_by_hash(tmp_path):
    src = tmp_path / "voice.wav"
    write_int16(src, np.full((1, 4800), 0.25, dtype=np.float32), 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src)
    (tmp_path / "moved").mkdir()
    moved = tmp_path / "moved" / "renamed.wav"
    src.rename(moved)
    fresh = MediaStore(tmp_path / "media", rate=48000)
    assert fresh.missing() == [media.id]
    assert fresh.relink(tmp_path) == {media.id: str(moved.resolve())}
    np.testing.assert_array_equal(fresh.read(media.id, 0, 10), decoded(moved)[:, :10])


def test_a_linked_file_that_changed_is_not_played(tmp_path):
    src = tmp_path / "voice.wav"
    write_int16(src, np.full((1, 4800), 0.25, dtype=np.float32), 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src)
    write_int16(src, np.full((1, 9600), -0.5, dtype=np.float32), 48000)
    fresh = MediaStore(tmp_path / "media", rate=48000)
    assert fresh.missing() == [media.id]
    assert not fresh.read(media.id, 0, 10).any()


def test_consolidate_makes_the_project_independent_of_the_source(tmp_path):
    src = tmp_path / "voice.wav"
    write_int16(src, np.full((1, 4800), 0.25, dtype=np.float32), 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src)
    want = decoded(src)
    store.consolidate()
    src.unlink()
    fresh = MediaStore(tmp_path / "media", rate=48000)
    assert not fresh.is_linked(media.id)
    np.testing.assert_array_equal(fresh.read(media.id, 0, 4800), want)


# -- every format: ffmpeg ------------------------------------------------------


def ffmpeg(*args):
    # Fixed argv, no shell; ffmpeg comes from PATH on purpose, as the app's own
    # binary lookup falls back to PATH too.
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)  # noqa: S603, S607


def test_compressed_audio_is_decoded_by_ffmpeg(tmp_path):
    src = tmp_path / "talk.m4a"
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=2:sample_rate=44100",
           "-c:a", "aac", str(src))
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src)
    assert media.channels == 1
    assert abs(media.frames - 2 * 48000) < 48000 * 0.1
    assert np.abs(store.read(media.id, 48000, 4800)).max() > 0.1


def test_audio_is_taken_from_video(tmp_path):
    src = tmp_path / "interview.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=2",
           "-f", "lavfi", "-i", "sine=frequency=300:duration=2:sample_rate=48000",
           "-ac", "2", "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(src))
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src)
    assert media.channels == 2
    # AAC coding lowers a 0.125-peak tone to about 0.09-0.10 (ffmpeg's own decode
    # gives 0.10), so 0.1 was never a valid bar; 0.05 still proves the audio is there.
    assert np.abs(store.read(media.id, 24000, 4800)).max() > 0.05


def test_two_files_sharing_an_id_prefix_are_refused(tmp_path):
    # docs/FORMAT.md: the id is 12 hex digits of the hash, so the full hash
    # is stored and checked. Fake the (astronomically unlikely) collision.
    src = tmp_path / "a.wav"
    write_int16(src, np.full((1, 480), 0.25, dtype=np.float32), 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    media = store.import_file(src)
    store.db.execute("update media set sha256=? where id=?", ("f" * 64, media.id))
    store._meta.clear()
    with pytest.raises(MediaError) as err:
        store.import_file(src)
    assert err.value.key == "error.media.id_collision"


def test_the_media_row_is_written_after_the_file(tmp_path, monkeypatch):
    # A crash while the working file is being written leaves no row, so
    # nothing looks imported.
    src = tmp_path / "a.wav"
    write_int16(src, np.full((1, 480), 0.25, dtype=np.float32), 48000)
    store = MediaStore(tmp_path / "media", rate=48000)

    def crash(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("kuulas.media._same_samples", crash)
    with pytest.raises(OSError, match="disk full"):
        store.import_file(src, copy=True)
    assert store.find(src) is None
    assert store.ids() == []


def test_the_same_bytes_imported_in_parallel_are_stored_once(tmp_path):
    # Two cores meeting the same file (a batch that lists it twice, or two
    # copies of it) must not both encode it: one wins, the others find the row.
    src = tmp_path / "a.wav"
    write_wav(src, np.ones((1, 48000 * 20), dtype=np.float32) * 0.1, 48000)
    copy = tmp_path / "b.wav"
    copy.write_bytes(src.read_bytes())
    store = MediaStore(tmp_path / "media", rate=48000)
    found = store.import_files([src, copy] * 4, copy=True)
    assert len({m.id for m in found}) == 1
    assert store.ids() == [found[0].id]


# -- the read path touches no database and hashes nothing (WP36) --------------------


def linked_store(tmp_path, seconds=25):
    src = tmp_path / "in.wav"
    write_wav(src, np.full((1, 48000 * seconds), 0.25, dtype=np.float32), 48000)
    store = MediaStore(tmp_path / "media", rate=48000)
    return src, store, store.import_file(src)


def test_read_issues_no_database_queries_after_the_first_meta_load(tmp_path):
    _, store, media = linked_store(tmp_path)
    store.read(media.id, 0, 100)
    queries = []
    store.db.set_trace_callback(queries.append)
    for first in (0, 500_000, 1_000_000, 100):  # several chunks, and a repeat
        store.read(media.id, first, 4800)
    store.db.set_trace_callback(None)
    assert queries == []


def test_read_never_rehashes_a_linked_file_whose_mtime_changed(tmp_path, monkeypatch):
    src, store, media = linked_store(tmp_path)
    store.close()
    os.utime(src, ns=(1, 1))  # same bytes, new mtime
    fresh = MediaStore(tmp_path / "media", rate=48000)  # validation happens here

    def no_hash(_path):
        raise AssertionError("read hashed a file")

    monkeypatch.setattr(media_module, "_sha256", no_hash)
    assert fresh.read(media.id, 0, 10).shape == (1, 10)
    assert fresh.missing() == []  # unchanged bytes, found valid at open


def test_a_linked_file_that_vanishes_after_open_plays_silence_after_a_check(tmp_path):
    src, store, media = linked_store(tmp_path, seconds=1)
    assert store.read(media.id, 0, 10).any()
    src.unlink()
    assert store.missing() == [media.id]  # the background check
    fresh = MediaStore(tmp_path / "media", rate=48000)
    assert not fresh.read(media.id, 0, 10).any()
