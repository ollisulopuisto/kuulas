"""The engine's skip list (WP18 "play as if cut"), without an audio device.

The engine plays the programme from ``at`` and jumps over each skipped range
with a short equal-power crossfade. Every test pulls blocks from the engine
(``_render`` or the fake stream's callback) and compares them with a
reference built here from one whole-programme ``mixer.mix``: the played
pieces end to end, and at each join the sum of the outgoing side faded by
cos and the incoming side faded by sin. Nothing here opens a real device or
plays a sound.
"""

import numpy as np
import pytest
import soundfile as sf
from test_engine import (
    RATE,
    Clock,
    FakeSession,
    MemoryStore,
    install_rig,
    make,
    noise,
    project_with,
    wav,
)

from kuulas import messages, mixer
from kuulas.engine import Engine
from kuulas.media import CHUNK_SEC, MediaStore
from kuulas.playplan import XFADE_S, PlaybackRequestError
from kuulas.session import Session

ATOL = 1e-6
SIZES = [1000, 333, 1024, 7, 2048]  # uneven blocks, as the golden test uses
#: Half of the crossfade at a join between long pieces.
H = round(XFADE_S * RATE / 2)


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def rig(monkeypatch):
    return install_rig(monkeypatch)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Talk.kuulas")
    yield s
    s.close()


def pull(engine, sizes=SIZES, limit=10_000) -> np.ndarray:
    """Every block the engine plays until it stops by itself."""
    blocks = []
    while engine.status()["playing"] and len(blocks) < limit:
        blocks.append(engine._render(sizes[len(blocks) % len(sizes)]))
    assert not engine.status()["playing"], "playback never ended"
    return np.concatenate(blocks) if blocks else np.zeros((0, 2), np.float32)


def pieces_of(lo: int, hi: int, skip) -> list[tuple[int, int]]:
    """The played stretches of [lo, hi): written out here independently of
    the engine's own normalisation."""
    played, at = [], lo
    for a, b in sorted((max(lo, a), min(hi, b)) for a, b in skip):
        if b <= a:
            continue
        if a > at:
            played.append((at, a))
        at = max(at, b)
    if hi > at:
        played.append((at, hi))
    return played


def reference(whole: np.ndarray, played: list[tuple[int, int]]):
    """``(frames, 2)`` reference output and the crossfade windows in it."""
    out = np.concatenate([whole[:, a:b] for a, b in played], axis=1).astype(np.float64)
    windows = []
    t = 0
    for k, (a, b) in enumerate(played):
        if k:
            pa, pb = played[k - 1]
            h = min(H, (pb - pa) // 2, (b - a) // 2)
            theta = (np.arange(2 * h) + 0.5) / (2 * h) * (np.pi / 2)
            gone = whole[:, pb - h:pb + h].astype(np.float64)
            come = whole[:, a - h:a + h].astype(np.float64)
            out[:, t - h:t + h] = gone * np.cos(theta) + come * np.sin(theta)
            windows.append((t - h, t + h))
        t += b - a
    return out.T.astype(np.float32), windows


def whole_mix(session) -> np.ndarray:
    project = session.state
    return mixer.mix(project, session.store, 0, project.length + RATE)


def assert_played(out, expected):
    """``out`` is ``expected``, then only the silence padding the last block."""
    assert len(out) >= len(expected)
    np.testing.assert_allclose(out[:len(expected)], expected, rtol=0, atol=ATOL)
    assert not out[len(expected):].any()


def outside(windows, n):
    mask = np.ones(n, dtype=bool)
    for a, b in windows:
        mask[a:b] = False
    return mask


# -- the audio -----------------------------------------------------------------


def test_a_skip_plays_the_pieces_joined_by_an_equal_power_crossfade(rig, clock):
    engine, session, _ = make(rig, clock)  # 2 s of noise
    skip = [(20000, 40000)]
    engine.play(0, skip=skip)
    out = pull(engine)
    played = pieces_of(0, session.state.length, skip)
    expected, windows = reference(whole_mix(session), played)
    mask = outside(windows, len(expected))
    # Outside the crossfade every sample is the programme's own.
    np.testing.assert_allclose(out[:len(expected)][mask], expected[mask], rtol=0,
                               atol=ATOL)
    # Inside it: cos on the way out, sin on the way in, nothing else.
    assert_played(out, expected)
    (a, b), = windows
    assert 10 <= (b - a) / RATE * 1000 <= 20


def test_the_crossfade_has_no_click_on_steady_audio(rig, clock):
    # A 200 Hz tone, skipped at a point where the phase jumps: a hard cut
    # would step by about the full amplitude in one sample.
    t = np.arange(2 * RATE) / RATE
    tone = (0.5 * np.sin(2 * np.pi * 200 * t))[None, :].astype(np.float32)
    engine, _, _ = make(rig, clock, {"m": tone})
    engine.play(0, skip=[(10000, 10000 + 61)])
    out = pull(engine)[:, 0]
    natural = np.abs(np.diff(out[:9000])).max()
    assert np.abs(np.diff(out)).max() <= 1.5 * natural


def test_several_ranges_unsorted_and_overlapping_play_as_their_union(rig, clock):
    engine, session, _ = make(rig, clock)
    engine.play(0, skip=[(60000, 70000), (5000, 9000), (8000, 12000), (12000, 13000)])
    out = pull(engine)
    played = pieces_of(0, session.state.length, [(5000, 13000), (60000, 70000)])
    expected, _ = reference(whole_mix(session), played)
    assert_played(out, expected)


def test_an_empty_skip_list_is_plain_playback(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(1000, skip=[])
    out = engine._render(1024)
    np.testing.assert_array_equal(out, mixer.mix(session.state, store, 1000, 1024).T)
    engine.play(1000, skip=None)
    np.testing.assert_array_equal(engine._render(1024), out)


def test_a_skip_at_the_very_start_starts_after_it_without_a_fade(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(0, skip=[(0, 10000)])
    assert engine.status()["position"] == 10000  # the playhead is past it at once
    out = engine._render(1024)
    np.testing.assert_array_equal(out, mixer.mix(session.state, store, 10000, 1024).T)


def test_a_skip_at_the_end_stops_where_it_begins(rig, clock):
    engine, session, store = make(rig, clock)
    length = session.state.length
    engine.play(length - 30000, skip=[(length - 10000, length + 5000)])
    out = pull(engine)
    assert len(out) >= 20000
    np.testing.assert_allclose(
        out[:20000], mixer.mix(session.state, store, length - 30000, 20000).T,
        rtol=0, atol=ATOL)  # no fade: it ends as play-to-a-point does
    assert not out[20000:].any()
    status = engine.status()
    assert not status["playing"]
    assert status["position"] == length


def test_a_skip_up_to_until_stops_there(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(0, until=30000, skip=[(20000, 50000)])
    out = pull(engine)
    np.testing.assert_allclose(out[:20000], mixer.mix(session.state, store, 0, 20000).T,
                               rtol=0, atol=ATOL)
    assert not out[20000:].any()
    assert engine.status()["position"] == 30000


def test_a_skip_longer_than_the_programme_plays_nothing_and_ends(rig, clock):
    engine, session, _ = make(rig, clock)
    length = session.state.length
    engine.play(5000, skip=[(0, 10 * length)])
    out = pull(engine)
    assert not out.any()
    status = engine.status()
    assert not status["playing"]
    assert status["position"] == length


# -- the playhead ----------------------------------------------------------------


def test_positions_are_programme_time_and_jump_over_the_skip(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0, skip=[(20000, 40000)])
    for _ in range(19):
        engine._render(1000)
    assert engine.status()["position"] == 19000
    engine._render(2000)  # through the join
    assert engine.status()["position"] == 41000
    assert engine.status()["skip"] == [[20000, 40000]]


def test_the_playhead_subtracts_latency_across_the_jump(rig, clock):
    rig.latency = 1000 / RATE
    engine, _, _ = make(rig, clock)
    engine.play(0, skip=[(20000, 40000)])
    for _ in range(20):
        engine._render(1050)  # 21000 played, 20000 heard: right at the join
    assert engine.status()["position"] == 40000
    engine._render(500)
    assert engine.status()["position"] == 40500


def test_seeking_into_a_skipped_range_lands_after_it(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(0, skip=[(20000, 40000)])
    engine._render(1024)
    engine.seek(30000)
    assert engine.status()["position"] == 40000
    np.testing.assert_array_equal(engine._render(512),
                                  mixer.mix(session.state, store, 40000, 512).T)


def test_seeking_before_a_skip_still_skips_it(rig, clock):
    engine, session, _ = make(rig, clock)
    engine.play(0, skip=[(20000, 40000)])
    engine._render(30000)
    engine.seek(10000)
    out = pull(engine)
    expected, _ = reference(whole_mix(session),
                            pieces_of(10000, session.state.length, [(20000, 40000)]))
    assert_played(out, expected)


def test_stop_during_the_crossfade_leaves_the_heard_frame(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0, skip=[(20000, 40000)])
    engine._render(20000 + H // 2)  # inside the second half of the crossfade
    engine.stop()
    status = engine.status()
    assert not status["playing"]
    assert status["position"] == 40000 + H // 2
    assert not engine._render(1024).any()


def test_a_new_play_without_skip_forgets_the_old_list(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(0, skip=[(20000, 40000)])
    engine._render(1024)
    engine.play(19000)
    assert engine.status()["skip"] == []
    np.testing.assert_array_equal(engine._render(2048),
                                  mixer.mix(session.state, store, 19000, 2048).T)


def test_a_malformed_skip_is_refused_and_nothing_changes(rig, clock):
    engine, _, _ = make(rig, clock)
    with pytest.raises(PlaybackRequestError) as caught:
        engine.play(0, skip=[(500, 100)])
    assert caught.value.key == "error.engine.bad_skip"
    assert not engine.status()["playing"]
    assert rig.streams == []


# -- through the callback, and when things fail ------------------------------------


def test_the_callback_plays_the_skip_and_never_raises(rig, clock):
    engine, session, _ = make(rig, clock)
    skip = [(0, 3000), (20000, 40000), (41000, 41500), (90000, 10**9)]
    engine.play(0, skip=skip)
    blocks = [rig.stream.pump(n) for n in [1024, 1, 1023, 4096] * 40]
    out = np.concatenate(blocks)
    assert np.isfinite(out).all()
    expected, _ = reference(whole_mix(session), pieces_of(0, session.state.length, skip))
    np.testing.assert_allclose(out[:len(expected)], expected, rtol=0, atol=ATOL)
    assert not out[len(expected):].any()
    assert engine.status()["failed_blocks"] == 0


def test_a_mixer_failure_during_a_skip_plays_silence_and_is_counted(rig, clock,
                                                                    monkeypatch):
    engine, session, _ = make(rig, clock)
    skip = [(20000, 40000)]
    engine.play(0, skip=skip)
    for _ in range(19):
        rig.stream.pump(1000)
    real_mix = mixer.mix

    def broken(*_args, **_kwargs):
        raise RuntimeError("mixer bug")

    monkeypatch.setattr(mixer, "mix", broken)
    out = rig.stream.pump(2000)  # the block with the join in it
    assert np.array_equal(out, np.zeros_like(out))
    monkeypatch.setattr(mixer, "mix", real_mix)
    status = engine.status()
    assert status["failed_blocks"] == 1
    assert status["playing"]
    engine._tick()
    assert "notice.engine.block_failed" in [n["key"] for n in engine.status()["notices"]]
    # The stream carries on with the block that failed, the join included.
    expected, _ = reference(whole_mix(session), pieces_of(0, session.state.length, skip))
    np.testing.assert_allclose(rig.stream.pump(2000), expected[19000:21000],
                               rtol=0, atol=ATOL)


def test_a_damaged_chunk_after_the_skip_plays_silence_and_marks_the_media(
        rig, clock, session, tmp_path, monkeypatch):
    session.import_media([str(wav(tmp_path / "long.wav", 25))])
    media_id = session.state.media[0].id
    real_chunk = MediaStore._chunk

    def chunk(self, mid, index):
        if index == 1:
            raise sf.LibsndfileError(0, "FLAC decode error")
        return real_chunk(self, mid, index)

    monkeypatch.setattr(MediaStore, "_chunk", chunk)
    engine = Engine(session, background=False, clock=clock)
    boundary = CHUNK_SEC * RATE
    engine.play(boundary - 30000, skip=[(boundary - 25000, boundary + 5000)])
    out = np.concatenate([engine._render(1024) for _ in range(20)])
    assert np.std(out[:4000]) > 0.01  # before the skip: chunk 0 plays
    assert not out[5000 + H:].any()  # after it: chunk 1, broken, is silence
    status = engine.status()
    assert status["playing"]
    assert status["failed_blocks"] == 0
    assert status["damaged"] == [media_id]


def test_with_device_resampling_the_skip_still_jumps(rig, clock):
    rig.refused_rates = {RATE}
    rig.device_rate = 44100.0
    arrays = {"m": noise(2)}
    store = MemoryStore(arrays)
    engine = Engine(FakeSession(project_with(arrays), store), background=False,
                    clock=clock)
    engine.play(0, skip=[(20000, 40000)])
    out = np.concatenate([rig.stream.pump(441) for _ in range(100)])  # 1 s
    assert np.isfinite(out).all()
    # 1 s heard of a programme with 20000 frames skipped
    assert abs(engine.status()["position"] - (RATE + 20000)) <= 2
