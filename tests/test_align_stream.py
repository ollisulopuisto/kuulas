"""Source envelopes never require the whole recording in memory."""

import numpy as np
import pytest

from kuulas.align_sound import envelope
from kuulas.align_stream import read_envelope


def test_chunked_channel_first_reader_matches_whole_source_at_nonzero_offset():
    rate = 8000
    rng = np.random.default_rng(8)
    audio = rng.normal(size=(2, rate*13+51)).astype(np.float32)
    calls = []

    def read(first, count):
        calls.append((first, count))
        return audio[:, first:first+count]

    result = read_envelope(read, rate=rate, start=31, frames=rate*12+11,
                           chunk_seconds=2)
    assert np.allclose(result, envelope(audio[:, 31:31+rate*12+11].T, rate))
    assert max(n for _, n in calls) <= rate*2
    assert calls[0][0] == 31
    assert calls[-1][0] + calls[-1][1] <= 31+rate*12+11


def test_limit_and_invalid_rate_fail_before_any_audio_read():
    def read(first, count):
        pytest.fail("must validate before reading")
    for args in [{"rate": 44100, "start": 0, "frames": 100},
                 {"rate": 8000, "start": -1, "frames": 100},
                 {"rate": 8000, "start": 0, "frames": 8000*61, "max_seconds": 60}]:
        with pytest.raises(ValueError, match="invalid or over-limit"):
            read_envelope(read, **args)


def test_cancel_checkpoint_between_bounded_reads(monkeypatch):
    seen = []
    def checkpoint():
        if seen:
            raise RuntimeError("cancelled")
    def read(first,count):
        seen.append(count)
        return np.ones((1,count),dtype=np.float32)
    monkeypatch.setattr("kuulas.align_stream.priority.checkpoint",checkpoint)
    with pytest.raises(RuntimeError,match="cancelled"):
        read_envelope(read,rate=8000,start=0,frames=8000*5,chunk_seconds=1)
    assert seen == [8000]


def test_truncated_and_invalid_channel_data_fail_closed():
    for read in [lambda first,count:np.zeros((1,count-1)),
                 lambda first,count:np.zeros((count,)),
                 lambda first,count:np.full((1,count),np.nan)]:
        with pytest.raises(ValueError, match=r"channel-first|finite project"):
            read_envelope(read,rate=8000,start=0,frames=8000)
