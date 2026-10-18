"""Loop playback in the engine (WP50), without an audio device.

``Engine.play(..., loop=(start, end))`` wraps from ``end`` back to ``start``
with the crossfade of a skip. Every test pulls blocks from the engine and
compares them with a reference built from one whole-programme ``mixer.mix``:
the same played pieces laid end to end that the skip tests use, with the
loop's range repeated. Nothing here opens a real device or plays a sound.
"""

import threading

import numpy as np
import pytest
from test_engine import RATE, Clock, install_rig, make, noise
from test_engine_skip import H, reference, whole_mix

from kuulas import messages, mixer
from kuulas.playplan import XFADE_S, PlaybackRequestError

SIZES = [1000, 333, 1024, 7, 2048]
S, E = 10000, 40000  # the loop used by most tests
L = E - S


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


def pull_n(engine, frames, sizes=SIZES) -> np.ndarray:
    """The next ``frames`` frames the engine plays, in uneven blocks."""
    blocks, have = [], 0
    while have < frames:
        n = min(sizes[len(blocks) % len(sizes)], frames - have)
        blocks.append(engine._render(n))
        have += n
    return np.concatenate(blocks)


def check(out, played, whole, trim=H):
    """``out`` is the reference for ``played``, up to ``trim`` frames before
    its end (where the reference stops fading and a loop goes on)."""
    expected, _ = reference(whole, played)
    n = min(len(expected) - trim, len(out))
    assert n > 0
    np.testing.assert_allclose(out[:n], expected[:n], rtol=0, atol=1e-6)


# -- the audio -----------------------------------------------------------------


def test_the_wrap_lands_on_the_loop_start_with_a_skips_crossfade(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    engine.play(S, loop=(S, E))
    out = pull_n(engine, 4 * L)
    check(out, [(S, E)] * 4, whole)
    # The first sample after the wrap's crossfade is the loop's own start.
    np.testing.assert_allclose(out[L + H], whole[:, S + H], rtol=0, atol=1e-6)
    assert engine.status()["playing"]  # and it does not stop by itself


def test_the_crossfade_is_15_ms_equal_power(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    engine.play(S, loop=(S, E))
    out = pull_n(engine, 2 * L)
    theta = (np.arange(2 * H) + 0.5) / (2 * H) * (np.pi / 2)
    gone = whole[:, E - H:E + H].astype(np.float64)
    come = whole[:, S - H:S + H].astype(np.float64)
    want = (gone * np.cos(theta) + come * np.sin(theta)).T
    np.testing.assert_allclose(out[L - H:L + H], want, rtol=0, atol=1e-6)
    assert pytest.approx(XFADE_S, abs=1e-3) == 2 * H / RATE


def test_the_wrap_has_no_click_on_steady_audio(rig, clock):
    t = np.arange(2 * RATE) / RATE
    tone = (0.5 * np.sin(2 * np.pi * 200 * t))[None, :].astype(np.float32)
    engine, _, _ = make(rig, clock, {"m": tone})
    engine.play(S, loop=(S, S + 10061))  # a length that does not fit the period
    out = pull_n(engine, 10061 * 5)[:, 0]
    natural = np.abs(np.diff(out[:9000])).max()
    assert np.abs(np.diff(out)).max() <= 1.5 * natural


def test_a_loop_over_a_skip_plays_the_skipped_version(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    engine.play(S, loop=(S, 50000), skip=[(20000, 30000)])
    out = pull_n(engine, 5 * 30000)
    check(out, [(S, 20000), (30000, 50000)] * 5, whole)


def test_a_play_from_before_the_loop_plays_the_lead_in_once(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    engine.play(5000, loop=(S, E))
    out = pull_n(engine, 35000 + 2 * L)
    check(out, [(5000, E), (S, E), (S, E)], whole)


def test_a_play_from_inside_the_loop_runs_to_its_end_then_wraps(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    engine.play(25000, loop=(S, E))
    out = pull_n(engine, 15000 + 2 * L)
    check(out, [(25000, E), (S, E), (S, E)], whole)


def test_a_play_from_past_the_loop_starts_at_its_start(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    engine.play(60000, loop=(S, E))
    assert engine.status()["position"] == S
    check(pull_n(engine, 2 * L), [(S, E)] * 2, whole)


def test_a_loop_from_the_very_start_fades_in_from_nothing(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    engine.play(0, loop=(0, 30000))
    out = pull_n(engine, 3 * 30000)
    theta = (np.arange(2 * H) + 0.5) / (2 * H) * (np.pi / 2)
    gone = whole[:, 30000 - H:30000 + H].astype(np.float64)
    come = np.concatenate([np.zeros((2, H)), whole[:, :H]], axis=1).astype(np.float64)
    want = (gone * np.cos(theta) + come * np.sin(theta)).T
    np.testing.assert_allclose(out[30000 - H:30000 + H], want, rtol=0, atol=1e-6)
    assert np.isfinite(out).all()


def test_a_loop_is_cut_at_the_end_of_the_project(rig, clock):
    engine, session, _ = make(rig, clock)
    length = session.state.length
    engine.play(length - 20000, loop=(length - 20000, length + 50000))
    assert engine.status()["loop"] == [length - 20000, length]


def test_the_loop_survives_a_seek(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    engine.play(S, loop=(S, E))
    engine._render(5000)
    engine.seek(30000)
    out = pull_n(engine, 10000 + 2 * L)
    check(out, [(30000, E), (S, E), (S, E)], whole)
    assert engine.status()["loop"] == [S, E]


def test_the_playhead_wraps_with_the_sound(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(S, loop=(S, E))
    pull_n(engine, L + 1000)
    assert engine.status()["position"] == S + 1000
    pull_n(engine, 5 * L)
    assert engine.status()["position"] == S + 1000
    assert engine.status()["playing"]


# -- changing the loop while it plays ------------------------------------------


def test_ending_the_loop_takes_effect_at_the_next_wrap(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    length = session.state.length
    engine.play(S, loop=(S, E))
    head = pull_n(engine, 1000)
    engine.play()  # no loop: go on
    out = np.concatenate([head, pull_n(engine, length - S - 1000 + 5000)])
    # The first pass runs through its end without a wrap, to the project's end.
    expected = whole[:, S:length].T
    np.testing.assert_allclose(out[:len(expected)], expected, rtol=0, atol=1e-6)
    assert not out[len(expected):].any()
    assert not engine.status()["playing"]
    assert engine.status()["loop"] is None


def test_ending_the_loop_after_a_few_wraps_goes_on_after_the_next_one(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    length = session.state.length
    engine.play(S, loop=(S, E))
    head = pull_n(engine, 2 * L + 5000)  # inside the third pass
    engine.play()
    out = np.concatenate([head, pull_n(engine, 90000)])
    expected, _ = reference(whole, [(S, E), (S, E), (S, E)])
    np.testing.assert_allclose(out[:3 * L - H], expected[:3 * L - H], rtol=0, atol=1e-6)
    # ... and from there the programme goes on past the old end, unfaded.
    tail = whole[:, E:length].T
    np.testing.assert_allclose(out[3 * L:3 * L + len(tail)], tail, rtol=0, atol=1e-6)


def test_changing_the_loop_takes_effect_at_the_next_wrap(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    engine.play(S, loop=(S, E))
    head = pull_n(engine, 1000)
    engine.play(loop=(20000, 30000))
    assert engine.status()["loop"] == [20000, 30000]
    out = np.concatenate([head, pull_n(engine, 4 * L)])
    check(out, [(S, E)] + [(20000, 30000)] * 12, whole)


def test_a_change_too_close_to_the_wrap_waits_for_the_one_after(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    engine.play(S, loop=(S, E))
    head = pull_n(engine, L - H // 2)  # already inside the wrap's crossfade
    engine.play(loop=(20000, 30000))
    out = np.concatenate([head, pull_n(engine, 3 * L)])
    check(out, [(S, E)] * 2 + [(20000, 30000)] * 9, whole)


def test_the_same_loop_again_changes_nothing(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    engine.play(S, loop=(S, E))
    head = pull_n(engine, 5000)
    engine.play(loop=(S, E))
    out = np.concatenate([head, pull_n(engine, 3 * L)])
    check(out, [(S, E)] * 4, whole)


def test_starting_a_loop_while_playing_loops_from_the_heard_frame(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)
    engine.play(0)
    engine._render(25000)
    engine.play(loop=(S, E))
    out = pull_n(engine, 15000 + 2 * L)
    check(out, [(25000, E), (S, E), (S, E)], whole)


# -- status, errors, the callback --------------------------------------------------


def test_status_reports_the_loop_while_it_plays(rig, clock):
    engine, _, _ = make(rig, clock)
    assert engine.status()["loop"] is None
    engine.play(S, loop=(S, E))
    assert engine.status()["loop"] == [S, E]
    engine.stop()
    assert engine.status()["loop"] is None
    engine.play(S)
    assert engine.status()["loop"] is None


@pytest.mark.parametrize("bad", [(E, S), (S, S), (-5, E), "x", (0, 10)])
def test_a_bad_loop_is_refused_and_nothing_changes(rig, clock, bad):
    engine, _, _ = make(rig, clock)
    with pytest.raises(PlaybackRequestError) as caught:
        engine.play(0, loop=bad)
    assert caught.value.key == "error.engine.bad_loop"
    assert not engine.status()["playing"]
    assert rig.streams == []


def test_a_loop_nothing_of_which_is_left_after_the_skips_is_refused(rig, clock):
    engine, _, _ = make(rig, clock)
    with pytest.raises(PlaybackRequestError) as caught:
        engine.play(0, loop=(S, E), skip=[(0, 50000)])
    assert caught.value.key == "error.engine.bad_loop"
    assert rig.streams == []


def test_a_loop_cannot_play_backward(rig, clock):
    engine, _, _ = make(rig, clock)
    with pytest.raises(PlaybackRequestError) as caught:
        engine.play(E, loop=(S, E), rate=-1.0)
    assert caught.value.key == "error.engine.bad_loop"
    assert rig.streams == []


def test_the_callback_loops_without_the_session_lock_or_failures(rig, clock):
    engine, session, _ = make(rig, clock)
    whole = whole_mix(session)

    class Forbidden:
        def __enter__(self):
            raise AssertionError("the audio thread took the session lock")

        def __exit__(self, *exc):
            return False

        acquire = release = __enter__

    session.lock = Forbidden()
    engine.play(S, loop=(S, E))
    outs = []

    def run():  # as PortAudio does: a thread of its own
        outs.extend(rig.stream.pump(n) for n in [1024, 1, 1023, 4096] * 60)

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    out = np.concatenate(outs)
    assert np.isfinite(out).all()
    assert engine.status()["failed_blocks"] == 0
    assert engine.status()["playing"]
    check(out, [(S, E)] * (len(out) // L), whole)


def test_a_loop_through_a_resampling_device_keeps_looping(rig, clock):
    rig.device_rate = 44100.0
    rig.refused_rates = {RATE}
    engine, _, _ = make(rig, clock, {"m": noise(2)})
    engine.play(S, loop=(S, E))
    out = np.concatenate([rig.stream.pump(1024) for _ in range(120)])
    assert np.isfinite(out).all()
    assert engine.status()["playing"]
    assert engine.status()["failed_blocks"] == 0
    assert np.abs(out[-1024:]).max() > 0


def test_a_loop_of_the_whole_project_starts_as_the_project_does(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(0, loop=(0, session.state.length))
    out = pull_n(engine, 5000)
    np.testing.assert_array_equal(out, mixer.mix(session.state, store, 0, 5000).T)
