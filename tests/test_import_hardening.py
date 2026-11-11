"""Import hardening (WP34): broken files cost that file, never the session.

Fault injection per docs/PLAN.md ground rule 13. The broken files come from
``tests/fixtures/broken/make_broken.py``.
"""

import errno
import os
import shutil
import stat
import struct
import time
from collections import namedtuple
from pathlib import PurePosixPath, PureWindowsPath

import numpy as np
import pytest
import soundfile as sf
from fixtures.broken.make_broken import RATE, add_bext, make_all, noise

from kuulas import media as media_mod
from kuulas import messages
from kuulas.media import MediaError, MediaStore, bwf_time_reference, drive_of
from kuulas.session import Session


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def broken(tmp_path):
    return make_all(tmp_path / "broken")


@pytest.fixture
def store(tmp_path):
    s = MediaStore(tmp_path / "media", rate=RATE)
    yield s
    s.close()


def leftovers(store):
    """Files in the media folder: nothing but finished work may stay."""
    return sorted(p.name for p in store.folder.rglob("*") if p.is_file())


def keys(result):
    return [n.key for n in result.warnings]


def fake_binary(tmp_path, name, body):
    script = tmp_path / f"fake-{name}"
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def use_fake(monkeypatch, name, script):
    real = media_mod.get_binary_path
    monkeypatch.setattr(media_mod, "get_binary_path",
                        lambda n: str(script) if n == name else real(n))


# -- the fixtures themselves ---------------------------------------------------


def test_every_broken_fixture_is_small(broken):
    assert {p.name for p in broken.values()} >= {
        "truncated.wav", "garbage.wav", "empty.wav", "junk_middle.mp3",
        "video_no_audio.mp4", "six_channel.wav", "nonsense_bwf.wav"}
    assert all(p.stat().st_size < 200_000 for p in broken.values())


# -- partial imports -----------------------------------------------------------


@pytest.mark.parametrize("copy", [False, True])
def test_a_truncated_wav_comes_in_as_far_as_it_goes(store, broken, copy):
    [r] = store.import_batch([broken["truncated.wav"]], copy=copy)
    assert r.ok
    assert 0 < r.media.frames < 2 * RATE
    partial = r.media.extra["partial"]
    assert partial["frames"] == r.media.frames
    assert partial["expected_frames"] == 2 * RATE
    [note] = r.warnings
    assert note.key == "warn.media.partial"
    assert "0:01 of 0:02" in str(note)
    # The audio that is there can be read.
    assert np.abs(store.read(r.media.id, 1000, 100)).max() > 0.01


def test_a_partial_import_is_still_marked_when_the_file_comes_again(store, broken):
    store.import_batch([broken["truncated.wav"]])
    [again] = store.import_batch([broken["truncated.wav"]])
    assert again.media.extra["partial"]["expected_frames"] == 2 * RATE
    assert keys(again) == ["warn.media.partial"]


def test_mp3_with_junk_in_the_middle_imports_what_decodes(store, broken):
    [r] = store.import_batch([broken["junk_middle.mp3"]])
    assert r.ok
    assert 0 < r.media.frames < 6 * RATE
    expected = r.media.extra["partial"]["expected_frames"]
    assert expected == pytest.approx(6 * RATE, abs=RATE // 10)
    assert keys(r) == ["warn.media.partial"]


def test_a_healthy_file_is_not_marked_partial(store, tmp_path):
    src = tmp_path / "ok.wav"
    sf.write(src, noise(1.0), RATE, subtype="PCM_16")
    [r] = store.import_batch([src])
    assert r.ok
    assert "partial" not in r.media.extra
    assert r.warnings == []


# -- refusals ------------------------------------------------------------------


def test_zero_length_file_is_refused_as_empty(store, broken):
    [r] = store.import_batch([broken["empty.wav"]])
    assert not r.ok
    assert r.error.key == "error.media.empty"
    assert "empty.wav" in str(r.error)
    assert store.ids() == []
    assert leftovers(store) == []


def test_garbage_header_is_refused_as_unreadable(store, broken):
    [r] = store.import_batch([broken["garbage.wav"]])
    assert r.error.key == "error.media.unreadable"
    assert store.ids() == []
    assert leftovers(store) == []


def test_video_without_audio_is_refused(store, broken):
    [r] = store.import_batch([broken["video_no_audio.mp4"]])
    assert r.error.key == "error.media.no_audio"
    assert store.ids() == []


def test_a_wav_with_no_frames_is_refused_as_empty(store, tmp_path):
    src = tmp_path / "none.wav"
    sf.write(src, np.zeros((0, 1), np.float32), RATE, subtype="PCM_16")
    [r] = store.import_batch([src])
    assert r.error.key == "error.media.empty"


def test_a_silent_file_is_flagged_but_comes_in(store, broken):
    [r] = store.import_batch([broken["silent.wav"]])
    assert r.ok
    assert keys(r) == ["warn.media.silent"]
    assert "silent.wav" in str(r.warnings[0])


# -- formats -------------------------------------------------------------------


def test_more_than_two_channels_are_downmixed_with_a_warning(store, broken):
    [r] = store.import_batch([broken["six_channel.wav"]])
    assert r.ok
    assert r.media.channels == 2
    [note] = r.warnings
    assert note.key == "warn.media.downmixed"
    assert note.params["channels"] == 6
    assert np.abs(store.read(r.media.id, 1000, 100)).max() > 0.01


def test_float_samples_are_decoded_fully_to_flac(store, broken):
    [r] = store.import_batch([broken["float32.wav"]])
    assert r.ok
    meta = store.meta(r.media.id)
    assert meta["storage"] == "working"
    assert store.working_file(r.media.id).is_file()
    assert r.media.frames == RATE // 2
    assert r.warnings == []


def test_a_bwf_time_far_outside_a_day_is_ignored_with_a_warning(store, broken):
    [r] = store.import_batch([broken["nonsense_bwf.wav"]])
    assert r.ok
    assert r.media.time_ref_flicks is None
    [note] = r.warnings
    assert note.key == "warn.media.bad_time_reference"
    assert note.params["hours"] > 24


def test_a_sane_bwf_time_is_kept_without_a_warning(store, tmp_path):
    src = tmp_path / "ok.wav"
    sf.write(src, noise(1.0), RATE, subtype="PCM_16")
    add_bext(src, 3600 * RATE)
    [r] = store.import_batch([src])
    assert r.media.time_ref_flicks is not None
    assert r.warnings == []


def test_rf64_chunks_are_sized_from_ds64(tmp_path):
    # An RF64 file stores 0xFFFFFFFF in the data chunk and the real size in
    # ds64. A 5 GB sparse file (no real disk used) with the bext chunk after
    # the audio: the reader must jump the real size to find it.
    path = tmp_path / "long.wav"
    data_bytes = 5 * 1024 ** 3
    fmt = struct.pack("<HHIIHH", 1, 1, RATE, RATE * 2, 2, 16)
    ds64 = struct.pack("<QQQI", 0, data_bytes, data_bytes // 2, 0)
    bext = bytearray(602)
    struct.pack_into("<Q", bext, 338, 7200 * RATE)
    with path.open("wb") as f:
        f.write(b"RF64" + struct.pack("<I", 0xFFFFFFFF) + b"WAVE")
        f.write(b"ds64" + struct.pack("<I", len(ds64)) + ds64)
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"data" + struct.pack("<I", 0xFFFFFFFF))
        f.seek(data_bytes, os.SEEK_CUR)
        f.write(b"bext" + struct.pack("<I", len(bext)) + bytes(bext))
    assert bwf_time_reference(path) == (7200 * RATE, RATE)


def test_a_small_rf64_wav_imports_bit_exactly(store, tmp_path):
    src = tmp_path / "rf.wav"
    sf.write(src, noise(1.0), RATE, format="RF64", subtype="PCM_16")
    [r] = store.import_batch([src])
    assert r.ok
    assert r.media.frames == RATE
    assert store.is_lossless(r.media.id)


# -- a batch -------------------------------------------------------------------


def test_one_bad_file_never_fails_a_batch(store, broken, tmp_path):
    good = tmp_path / "good.wav"
    sf.write(good, noise(1.0, seed=9), RATE, subtype="PCM_16")
    order = [broken["garbage.wav"], good, broken["empty.wav"],
             broken["truncated.wav"], broken["video_no_audio.mp4"]]
    results = store.import_batch(order)
    assert [r.path.name for r in results] == [p.name for p in order]
    assert [r.ok for r in results] == [False, True, False, True, False]
    assert [r.error.key for r in results if not r.ok] == [
        "error.media.unreadable", "error.media.empty", "error.media.no_audio"]
    assert len(store.ids()) == 2


def test_import_files_still_returns_media_and_raises_after_trying_everything(
        store, broken, tmp_path):
    good = tmp_path / "good.wav"
    sf.write(good, noise(1.0, seed=9), RATE, subtype="PCM_16")
    with pytest.raises(MediaError):
        store.import_files([broken["garbage.wav"], good])
    assert len(store.ids()) == 1


def test_an_unexpected_failure_is_reported_for_that_file_only(
        store, tmp_path, monkeypatch):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    sf.write(a, noise(1.0, seed=1), RATE, subtype="PCM_16")
    sf.write(b, noise(1.0, seed=2), RATE, subtype="PCM_16")
    real = MediaStore._import_once

    def flaky(self, path, *args, **kwargs):
        if path.name == "a.wav":
            raise ValueError("boom")
        return real(self, path, *args, **kwargs)

    monkeypatch.setattr(MediaStore, "_import_once", flaky)
    ra, rb = store.import_batch([a, b])
    assert ra.error.key == "error.media.failed"
    assert "boom" in str(ra.error)
    assert rb.ok


def test_a_session_imports_what_it_can_and_reports_the_rest(tmp_path, broken):
    s = Session(tmp_path / "Talk.kuulas")
    try:
        good = tmp_path / "good.wav"
        sf.write(good, noise(1.0, seed=9), RATE, subtype="PCM_16")
        p, report = s.import_media_report(
            [str(broken["garbage.wav"]), str(good), str(broken["truncated.wav"])])
        assert [t.name for t in p.tracks] == ["good", "truncated"]
        assert [r.ok for r in report] == [False, True, True]
        assert s.last_import_report == report
        assert keys(report[2]) == ["warn.media.partial"]
        assert len([n for n in s.history.nodes() if n["label"].startswith("Import")]) == 1
    finally:
        s.close()


def test_a_session_whose_every_file_fails_changes_nothing(tmp_path, broken):
    s = Session(tmp_path / "Talk.kuulas")
    try:
        with pytest.raises(MediaError) as err:
            s.import_media([str(broken["garbage.wav"]), str(broken["empty.wav"])])
        assert err.value.key == "error.media.all_failed"
        assert "garbage.wav" in str(err.value)
        assert "empty.wav" in str(err.value)
        assert s.state.tracks == ()
        assert not s.history.can_undo
    finally:
        s.close()


# -- hung decoders -------------------------------------------------------------


def test_a_hung_ffprobe_is_killed_and_reported(store, broken, tmp_path, monkeypatch):
    use_fake(monkeypatch, "ffprobe", fake_binary(tmp_path, "ffprobe", "exec sleep 30\n"))
    monkeypatch.setattr(media_mod, "PROBE_TIMEOUT_SEC", 0.5)
    [r] = store.import_batch([broken["junk_middle.mp3"]])
    assert r.error.key == "error.media.probe_timeout"
    assert store.ids() == []


def test_a_hung_ffmpeg_is_killed_and_reported(store, broken, tmp_path, monkeypatch):
    pidfile = tmp_path / "pid"
    script = fake_binary(tmp_path, "ffmpeg", f'echo $$ > "{pidfile}"\nexec sleep 30\n')
    use_fake(monkeypatch, "ffmpeg", script)

    real_monotonic = time.monotonic
    start = real_monotonic()

    def fake_monotonic() -> float:
        now = real_monotonic()
        if pidfile.exists() or (now - start) > 10.0:
            return start + 100.0
        return start

    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    monkeypatch.setattr(media_mod, "STALL_SEC", 0.1)
    [r] = store.import_batch([broken["junk_middle.mp3"]])
    assert r.error.key == "error.media.decode_timeout"
    assert leftovers(store) == []
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


# -- free space and full disks -------------------------------------------------


Usage = namedtuple("Usage", "total used free")


def test_not_enough_free_space_is_refused_before_decoding(store, broken, monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage", lambda _p: Usage(10**9, 10**9 - 1000, 1000))
    [r] = store.import_batch([broken["junk_middle.mp3"]])
    assert r.error.key == "error.media.disk_full"
    assert r.error.params["needed"] > r.error.params["free"]
    assert "MB" in str(r.error)
    assert leftovers(store) == []
    assert store.ids() == []


def test_enough_free_space_does_not_get_in_the_way(store, broken, monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage", lambda _p: Usage(10**12, 0, 10**12))
    [r] = store.import_batch([broken["junk_middle.mp3"]])
    assert r.ok


@pytest.mark.parametrize("name", ["six_channel.wav", "junk_middle.mp3"])
def test_a_disk_that_fills_mid_import_loses_the_partial_file(
        store, broken, monkeypatch, name):
    def full(_chunk):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(media_mod, "_peaks", full)
    [r] = store.import_batch([broken[name]], copy=True)
    assert r.error.key == "error.media.disk_full"
    assert r.error.params["needed"] > 0
    assert leftovers(store) == []
    assert store.ids() == []


# -- a source that disappears --------------------------------------------------


def test_drive_names():
    assert drive_of(PurePosixPath("/Volumes/ZOOM H6/rec/a.wav")) == "ZOOM H6"
    assert drive_of(PurePosixPath("/media/dst/USB STICK/a.wav")) == "USB STICK"
    assert drive_of(PurePosixPath("/run/media/dst/CARD/a.wav")) == "CARD"
    assert drive_of(PurePosixPath("/mnt/disk2/a.wav")) == "disk2"
    assert drive_of(PurePosixPath("/Users/me/a.wav")) == "/"
    assert drive_of(PureWindowsPath("E:/rec/a.wav")) == "E:"


def test_a_drive_that_vanishes_mid_import_names_the_drive(store, broken, monkeypatch):
    monkeypatch.setattr(media_mod, "drive_of", lambda _p: "ZOOM H6")

    def gone(_chunk):
        raise OSError(errno.ENXIO, "Device not configured")

    monkeypatch.setattr(media_mod, "_peaks", gone)
    [r] = store.import_batch([broken["six_channel.wav"]], copy=True)
    assert r.error.key == "error.media.source_vanished"
    assert r.error.params["drive"] == "ZOOM H6"
    assert "ZOOM H6" in str(r.error)
    assert leftovers(store) == []
    assert store.ids() == []


def test_a_decoder_that_loses_its_source_reports_the_drive(store, broken, tmp_path,
                                                            monkeypatch):
    # The fake ffmpeg deletes its input (the drive is pulled), then fails.
    script = fake_binary(tmp_path, "ffmpeg", 'rm -f "$5"\nexit 1\n')
    use_fake(monkeypatch, "ffmpeg", script)
    src = tmp_path / "unplugged.mp3"
    shutil.copy(broken["junk_middle.mp3"], src)
    [r] = store.import_batch([src])
    assert r.error.key == "error.media.source_vanished"
    assert leftovers(store) == []
