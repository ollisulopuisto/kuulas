"""The browser's cursor against what is heard, simulated, at every speed (no device).

Owner report (2026-10-20, v26.10.20.2): at 1.75x with the pitch kept, pressing Space
makes the cursor jump back a bit. A jump back means the cursor the page extrapolated
was ahead of where the engine said the sound stopped.

The rig: a fake stream calls the engine every block on a fake clock, with a device
latency; output frame ``n`` (counted from the run's first callback at ``t0``) reaches
the ear at ``t0 + latency - block + n / rate`` (``stream.latency`` is the block plus
the DAC lead, as measured on Core Audio; docs/PLAYBACK-LATENCY.md). The right channel
of the media is a ramp, ``frame * SCALE``, so the right channel of what is heard *is*
the programme frame heard: through the WSOLA stretcher it is the window-weighted
mean of the grains' frames (the windows sum to one). The left channel is noise, so the
stretcher's grain search sees something like real sound, not the ramp.

Against that ground truth: the anchors ``engine.status()`` gives, extrapolated with
the arithmetic of ``ui/playhead-clock.js`` (``project``: frame + elapsed x speed x
rate), and the frame ``engine.stop()`` leaves the playhead at.
"""

import numpy as np
import pytest
from test_engine import RATE, Clock, install_rig, make, noise

from kuulas import messages, mixer

SCALE = 2.0 ** -28  # the ramp: frame 240000 is 9e-4, under the noise, exact in float32
BLOCK = 1024
LATENCY = 0.035  # the Mac Studio's internal speakers (docs/PLAYBACK-LATENCY.md)
MS = RATE / 1000  # frames per millisecond of programme
CORRECT_EVERY = 10  # blocks between anchors: about the live channel's 200 ms

SPEEDS = [(1.0, False), (1.5, False), (2.0, False),
          (1.5, True), (1.75, True), (2.0, True), (0.75, True)]


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


def project(anchor, now):
    """``ui/playhead-clock.js`` ``project`` for a forward run with no skips."""
    if not anchor["playing"]:
        return anchor["position"]
    return anchor["position"] + max(0.0, now - anchor["t"]) * anchor["speed"] * RATE


class Sim:
    """One run at ``speed``: callbacks every block from ``t0``, an anchor every
    ``CORRECT_EVERY`` blocks (read a third of a block after a callback)."""

    def __init__(self, monkeypatch, speed, stretch, latency=LATENCY):
        self.rig = install_rig(monkeypatch)
        self.rig.latency = latency
        self.latency = latency
        self.clock = Clock()
        frames = 8 * RATE
        ramp = (np.arange(frames) * SCALE).astype(np.float32)
        self.engine, session, store = make(
            self.rig, self.clock, {"m": np.stack([noise(8)[0], ramp])})
        # the mixer's gain on the right channel (pan law), measured, not assumed
        self.gain = float(mixer.mix(session.state, store, 1000, 1)[1, 0]) / (1000 * SCALE)
        self.t0 = self.clock.now
        self.engine.play(0, rate=speed, preserve_pitch=stretch)
        self.out: list[np.ndarray] = []
        self.anchors: list[dict] = []
        self.k = 0

    def pump(self, blocks):
        for _ in range(blocks):
            self.clock.now = self.t0 + self.k * BLOCK / RATE
            self.out.append(self.rig.stream.pump()[:, 1].copy())
            if self.k % CORRECT_EVERY == CORRECT_EVERY // 2:
                self.clock.now += BLOCK / RATE / 3
                self.anchors.append(self.engine.status())
            self.k += 1

    def truth(self, now):
        """The programme frame at the ear at ``now``."""
        heard = np.concatenate(self.out) / (self.gain * SCALE)
        n = (now - self.t0 - self.latency) * RATE + BLOCK
        return float(heard[round(n)])

    def cursor(self, now):
        """Where the page draws the playhead at ``now``: the newest anchor dated
        before ``now``, extrapolated."""
        anchor = [a for a in self.anchors if a["t"] <= now][-1]
        return project(anchor, now)


@pytest.mark.parametrize(("speed", "stretch"), SPEEDS)
def test_the_cursor_is_where_the_sound_is(monkeypatch, speed, stretch):
    sim = Sim(monkeypatch, speed, stretch)
    sim.pump(120)  # 2.6 s
    errors = []
    for k in range(20, 118):
        for phase in (0.1, 0.37, 0.8):
            now = sim.t0 + (k + phase) * BLOCK / RATE
            errors.append(sim.cursor(now) - sim.truth(now))
    errors = np.array(errors) / MS
    # Tape speeds: exact. Stretched: on average within 2.5 ms of programme (before
    # the fix 10, 15 and 20 ms ahead at 1.5x, 1.75x and 2x, 6 ms behind at 0.75x).
    # The grain search moves each grain up to 8 ms (stretch.SEARCH_S), so single
    # readings stray (spread about 4 ms); on noise it also leans towards the natural
    # continuation, which leaves about 1.6 ms of bias at 0.75x.
    assert abs(errors.mean()) < (2.5 if stretch else 0.05), errors.mean()
    assert np.abs(errors).max() < (12.0 if stretch else 0.05), np.abs(errors).max()


@pytest.mark.parametrize(("speed", "stretch"), SPEEDS)
@pytest.mark.parametrize("into_block", [0.1, 0.5, 0.95])
def test_stop_lands_where_the_cursor_is(monkeypatch, speed, stretch, into_block):
    """Space freezes the cursor at its extrapolated frame; the stop's answer must
    land within 2 ms of programme of it, however long after a callback it came."""
    sim = Sim(monkeypatch, speed, stretch)
    sim.pump(40)
    now = sim.t0 + (sim.k - 1 + into_block) * BLOCK / RATE
    cursor = sim.cursor(now)
    sim.clock.now = now
    sim.engine.stop()
    stopped = sim.engine.status()["position"]
    assert abs(stopped - cursor) < 2.0 * MS, (stopped - cursor) / MS
    assert abs(stopped - sim.truth(now)) < (9.0 if stretch else 1.0) * MS


def test_a_stalled_device_does_not_carry_the_stop_past_what_was_sent(monkeypatch):
    """No callback for a long while (the device stalled): the playhead at a stop is
    never past the last frame handed to the device."""
    sim = Sim(monkeypatch, 1.0, False)
    sim.pump(20)
    sent = 20 * BLOCK
    sim.clock.now += 1.0
    sim.engine.stop()
    assert sim.engine.status()["position"] <= sent
