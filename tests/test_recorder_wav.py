"""kuulas_recorder.wavfile: a WAV that is valid at every moment, and its repair.

The owner's rule (WP12): audio already recorded is never lost. A file from a
killed recorder must open with everything up to the last flush, and a file cut
short by a power loss is repaired, never discarded.
"""

import errno
import os
import struct

import numpy as np
import pytest
import soundfile as sf

from kuulas_recorder import wavfile
from kuulas_recorder.wavfile import ProgressiveWav, WavRepairError, repair_wav, wav_frames

RATE = 48000


def counter(first: int, n: int) -> np.ndarray:
    """Samples whose 24-bit value is the frame number: exact in float32 and PCM."""
    ints = (np.arange(first, first + n) % (1 << 20)) - (1 << 19)
    return (ints / float(1 << 23)).astype(np.float32)


def as_ints(path) -> np.ndarray:
    data, _ = sf.read(path, dtype="int32")
    return data >> 8  # soundfile scales 24-bit up to 32-bit


def test_header_generation():
    """The wav header function should return exactly 44 bytes and have
    correct RIFF chunk values."""
    rate = 48000
    data_bytes = 0
    head = wavfile.header(rate, data_bytes)
    assert len(head) == 44

    unpacked = struct.unpack("<4sI4s4sIHHIIHH4sI", head)
    # Fields: RIFF, 36+data_bytes, WAVE, fmt , 16, 1, 1, rate, rate * 3,
    # 3, 24, data, data_bytes
    assert unpacked[0] == b"RIFF"
    assert unpacked[1] == 36 + data_bytes
    assert unpacked[2] == b"WAVE"
    assert unpacked[3] == b"fmt "
    assert unpacked[4] == 16
    assert unpacked[5] == 1  # format PCM
    assert unpacked[6] == 1  # channels (mono)
    assert unpacked[7] == rate
    assert unpacked[8] == rate * 3  # byte rate
    assert unpacked[9] == 3  # block align
    assert unpacked[10] == 24  # bits per sample
    assert unpacked[11] == b"data"
    assert unpacked[12] == data_bytes

    rate2 = 44100
    data_bytes2 = 12000
    head2 = wavfile.header(rate2, data_bytes2)
    assert len(head2) == 44
    unpacked2 = struct.unpack("<4sI4s4sIHHIIHH4sI", head2)
    assert unpacked2[1] == 36 + data_bytes2
    assert unpacked2[7] == rate2
    assert unpacked2[8] == rate2 * 3
    assert unpacked2[12] == data_bytes2


def test_pcm24_round_trips_and_clips():
    x = np.array([0.0, 0.5, -0.5, 1.0, -1.0, 2.0, -2.0, 1 / (1 << 23)], np.float32)
    raw = wavfile.float_to_pcm24(x)
    assert len(raw) == 3 * len(x)
    vals = [int.from_bytes(raw[i:i + 3], "little", signed=True)
            for i in range(0, len(raw), 3)]
    assert vals == [0, 1 << 22, -(1 << 22), (1 << 23) - 1, -(1 << 23), (1 << 23) - 1,
                    -(1 << 23), 1]


def test_float_to_pcm24_empty():
    assert wavfile.float_to_pcm24([]) == b""


def test_float_to_pcm24_list_input():
    assert wavfile.float_to_pcm24([0.0, 0.5]) == b'\x00\x00\x00\x00\x00@'


def test_float_to_pcm24_nan_inf():
    with pytest.warns(RuntimeWarning, match="invalid value encountered in cast"):
        raw = wavfile.float_to_pcm24(np.array([np.nan, np.inf, -np.inf]))
    assert raw == b'\x00\x00\x00\xff\xff\x7f\x00\x00\x80'


def test_new_file_is_a_valid_empty_wav(tmp_path):
    path = tmp_path / "a.wav"
    w = ProgressiveWav(path, RATE)
    info = sf.info(path)
    assert (info.samplerate, info.channels, info.frames, info.subtype) == (
        RATE, 1, 0, "PCM_24")
    w.close()


def test_file_is_valid_after_every_flush(tmp_path):
    path = tmp_path / "a.wav"
    w = ProgressiveWav(path, RATE)
    written = 0
    for step in range(5):
        n = 1000 + 37 * step
        w.write(wavfile.float_to_pcm24(counter(written, n)))
        written += n
        w.flush()
        info = sf.info(path)
        assert info.frames == written
        ints = as_ints(path)
        assert np.array_equal(ints, (np.arange(written) % (1 << 20)) - (1 << 19))
    w.close()
    assert sf.info(path).frames == written


def test_unflushed_tail_never_makes_the_file_unreadable(tmp_path):
    path = tmp_path / "a.wav"
    w = ProgressiveWav(path, RATE)
    w.write(wavfile.float_to_pcm24(counter(0, 4800)))
    w.flush()
    w.write(wavfile.float_to_pcm24(counter(4800, 999)))  # not flushed yet
    info = sf.info(path)
    assert info.frames == 4800  # the header still says the last flush
    assert len(as_ints(path)) == 4800
    w.close()


def test_existing_file_is_never_overwritten(tmp_path):
    path = tmp_path / "a.wav"
    path.write_bytes(b"precious")
    with pytest.raises(FileExistsError):
        ProgressiveWav(path, RATE)
    assert path.read_bytes() == b"precious"


def test_room_counts_down_to_the_size_limit(tmp_path):
    w = ProgressiveWav(tmp_path / "a.wav", RATE, max_data_bytes=30)
    assert w.room_frames() == 10
    w.write(b"\0" * 12)
    assert w.room_frames() == 6
    with pytest.raises(ValueError, match="limit"):
        w.write(b"\0" * 21)
    w.close()


def test_default_limit_stays_under_the_riff_32_bit_size():
    assert wavfile.MAX_DATA_BYTES % 3 == 0
    assert wavfile.HEADER_BYTES + wavfile.MAX_DATA_BYTES < 0xFFFFFFFF


def test_full_disk_keeps_the_file_valid_with_what_was_written(tmp_path, monkeypatch):
    path = tmp_path / "a.wav"
    w = ProgressiveWav(path, RATE)
    w.write(wavfile.float_to_pcm24(counter(0, 100)))
    w.flush()
    real_write = os.write

    def half_then_full(fd, data):
        if fd == w.fileno() and len(data) > 3:
            real_write(fd, bytes(data)[:5])  # a partial frame lands, then no space
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", half_then_full)
    with pytest.raises(OSError, match="No space") as e:
        w.write(wavfile.float_to_pcm24(counter(100, 100)))
    assert e.value.errno == errno.ENOSPC
    monkeypatch.undo()
    w.close()
    assert sf.info(path).frames == 100
    assert os.path.getsize(path) == wavfile.HEADER_BYTES + 300


# --- repair -----------------------------------------------------------------


def write_counter_file(path, frames: int, *, flush: bool = True) -> None:
    w = ProgressiveWav(path, RATE)
    w.write(wavfile.float_to_pcm24(counter(0, frames)))
    if flush:
        w.flush()
    w.abandon()  # like a SIGKILL: no final header update


def test_repair_recovers_frames_written_after_the_last_flush(tmp_path):
    path = tmp_path / "a.wav"
    w = ProgressiveWav(path, RATE)
    w.write(wavfile.float_to_pcm24(counter(0, 1000)))
    w.flush()
    w.write(wavfile.float_to_pcm24(counter(1000, 500)))
    w.abandon()
    assert sf.info(path).frames == 1000
    result = repair_wav(path)
    assert result.frames == 1500
    assert result.changed
    assert np.array_equal(as_ints(path), (np.arange(1500) % (1 << 20)) - (1 << 19))


def test_repair_trims_a_trailing_partial_frame(tmp_path):
    path = tmp_path / "a.wav"
    write_counter_file(path, 1000)
    with open(path, "ab") as f:
        f.write(b"\x01\x02")  # two bytes of a frame that never finished
    result = repair_wav(path)
    assert result.frames == 1000
    assert result.trimmed_bytes == 2
    assert os.path.getsize(path) == wavfile.HEADER_BYTES + 3000
    assert sf.info(path).frames == 1000


def test_repair_fixes_a_header_that_claims_more_than_the_file_holds(tmp_path):
    path = tmp_path / "a.wav"
    write_counter_file(path, 1000)
    os.truncate(path, wavfile.HEADER_BYTES + 3 * 600 + 1)  # a power cut mid-file
    result = repair_wav(path)
    assert result.frames == 600
    assert sf.info(path).frames == 600
    assert np.array_equal(as_ints(path), (np.arange(600) % (1 << 20)) - (1 << 19))


def test_repair_leaves_a_good_file_alone(tmp_path):
    path = tmp_path / "a.wav"
    w = ProgressiveWav(path, RATE)
    w.write(wavfile.float_to_pcm24(counter(0, 10)))
    w.close()
    before = path.read_bytes()
    result = repair_wav(path)
    assert (result.frames, result.changed) == (10, False)
    assert path.read_bytes() == before


def test_repair_rebuilds_a_header_cut_short(tmp_path):
    path = tmp_path / "a.wav"
    full = ProgressiveWav(path, RATE)
    full.abandon()
    os.truncate(path, 20)  # the header itself never reached the disk
    result = repair_wav(path, rate=RATE)
    assert result.frames == 0
    info = sf.info(path)
    assert (info.frames, info.samplerate) == (0, RATE)


def test_repair_handles_streaming_size_placeholders(tmp_path):
    """Some recorders write 0 or 0xFFFFFFFF as the size until they stop."""
    path = tmp_path / "a.wav"
    write_counter_file(path, 50)
    with open(path, "r+b") as f:
        f.seek(4)
        f.write(struct.pack("<I", 0xFFFFFFFF))
        f.seek(40)
        f.write(struct.pack("<I", 0))
    assert repair_wav(path).frames == 50
    assert sf.info(path).frames == 50


def test_repair_refuses_a_file_that_is_not_a_wav(tmp_path):
    path = tmp_path / "a.wav"
    path.write_bytes(b"ID3" + b"\0" * 100)
    with pytest.raises(WavRepairError) as e:
        repair_wav(path)
    assert e.value.key == "not_a_wav"
    assert path.read_bytes() == b"ID3" + b"\0" * 100


# --- wav_frames -------------------------------------------------------------


def test_wav_frames_valid_and_empty(tmp_path):
    path = tmp_path / "test.wav"
    w = ProgressiveWav(path, RATE)
    assert wav_frames(path) == 0

    n_frames = 1200
    w.write(wavfile.float_to_pcm24(counter(0, n_frames)))
    w.flush()
    assert wav_frames(path) == n_frames

    # Unflushed audio is not reflected in the header, so wav_frames returns flushed count.
    w.write(wavfile.float_to_pcm24(counter(n_frames, 500)))
    assert wav_frames(path) == n_frames
    w.close()


def test_wav_frames_non_wav_and_missing_data(tmp_path):
    not_wav = tmp_path / "invalid.wav"
    not_wav.write_bytes(b"not a wav file header content")
    assert wav_frames(not_wav) == 0

    no_data_chunk = tmp_path / "no_data.wav"
    # Header with fmt chunk but no data chunk
    head = struct.pack(
        "<4sI4s4sIHHIIHH",
        b"RIFF", 28, b"WAVE", b"fmt ", 16, 1, 1, RATE, RATE * 3, 3, 24,
    )
    no_data_chunk.write_bytes(head)
    assert wav_frames(no_data_chunk) == 0
