"""One mixer for playback and export.

``mix`` renders any stretch of the timeline to stereo. The playback engine
calls it block by block and the exporter calls it minute by minute, so the
file you export is the mix you heard.

Signal flow::

    clip (gain, envelope, fades, pan) -> track (automation, gain, pan,
    mute/solo) -> bus (gain, pan, mute) or master -> master gain

Pan laws come from speechmix (``stems.pan_gains``): a mono clip is placed
with the constant-power law, so it measures the same loudness wherever it
sits; a stereo signal is balanced.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Protocol

import numpy as np
from speechmix.stems import pan_gains

from . import curves, perf
from .model import Clip, Project, Track

#: Ramp at each edge of a gated range, derived here and never stored. The
#: same 30 ms ``MUTE_RAMP_SEC`` gives the open piece beside a muted one:
#: a gate that snaps shut on room tone clicks, and 30 ms is inaudible as a
#: fade. The ramp lies in the open stretch, so the gated frames themselves
#: are exact silence.
GATE_RAMP_SEC = 0.030

#: Ramp on the edge of an open clip that touches a muted piece of contiguous
#: source on the same track (what ``mute_ranges`` leaves). Derived here from
#: the neighbour and never stored, so unmuting restores the audio exactly.
#: It lies inside the open piece; the muted frames stay exact silence.
MUTE_RAMP_SEC = 0.030


class Store(Protocol):
    def read(self, media_id: str, first: int, count: int) -> np.ndarray:
        """``(channels, count)`` float32 from source frame ``first``, zero-padded."""
        ...


def _ramp(t: np.ndarray, begin: int, length: int) -> np.ndarray:
    """Raised-sine rise from 0 at ``begin`` to 1 at ``begin + length``.

    Rise and fall of the same length sum to exactly 1 (sin² + cos²), so a
    crossfade over steady audio neither dips nor bumps.
    """
    x = np.clip((t - begin) / length, 0.0, 1.0)
    return np.sin(0.5 * np.pi * x) ** 2


def _gate_gain(gate: tuple[tuple[int, int], ...], first: int, count: int,
               rate: int) -> np.ndarray | None:
    """The track gate as gain over ``[first, first+count)``, or None when no
    gated range or ramp touches it (then the block is left alone).

    A function of the absolute frame only, so any chunking of the timeline
    gives the same gain: the ramp is neither repeated nor cut at a block
    edge. Applied to the track's sum, never per clip, so overlapping or
    crossfading clips are not ramped twice.
    """
    if not gate:
        return None
    ramp = max(1, round(GATE_RAMP_SEC * rate))
    end = first + count
    # Ranges are sorted and disjoint, so their ends are sorted too: start at
    # the last range that begins before this block's reach and walk on.
    i = max(0, bisect_left(gate, (first - ramp,)) - 1)
    g = None
    while i < len(gate) and gate[i][0] < end + ramp:
        a, b = gate[i]
        i += 1
        if b + ramp <= first:
            continue
        if g is None:
            g = np.ones(count, dtype=np.float64)
        lo, hi = max(a, first), min(b, end)
        if hi > lo:
            g[lo - first:hi - first] = 0.0
        lo, hi = max(a - ramp, first), min(a, end)
        if hi > lo:  # closing: the last open frame (a-1) is at 0
            t = np.arange(lo, hi, dtype=np.float64)
            g[lo - first:hi - first] *= _ramp(-t, -(a - 1), ramp)
        lo, hi = max(b, first), min(b + ramp, end)
        if hi > lo:  # opening: frame b is at 0
            t = np.arange(lo, hi, dtype=np.float64)
            g[lo - first:hi - first] *= _ramp(t, b, ramp)
    return g


def _mute_ramps(track: Track, rate: int) -> dict[str, tuple[int, int]]:
    """Derived ``{clip id: (ramp_in, ramp_out)}`` for open clips whose edge
    touches a muted piece of the same media with contiguous source."""
    after = {(c.media, c.start, c.offset) for c in track.clips if c.muted}
    before = {(c.media, c.end, c.offset + c.length) for c in track.clips if c.muted}
    if not after and not before:
        return {}
    ramp = max(1, round(MUTE_RAMP_SEC * rate))
    out = {}
    for c in track.clips:
        if c.muted:
            continue
        r_in = min(ramp, c.length) if (c.media, c.start, c.offset) in before else 0
        r_out = (min(ramp, c.length)
                 if (c.media, c.end, c.offset + c.length) in after else 0)
        if r_in or r_out:
            out[c.id] = (r_in, r_out)
    return out


def _clip_signal(clip: Clip, store: Store, first: int, count: int,
                 ramps: tuple[int, int] = (0, 0)) -> tuple[int, int, np.ndarray] | None:
    """The clip's own sound over ``[first, first+count)``: ``(lo, hi, audio)``
    with ``audio`` ``(channels, hi-lo)`` float64 after clip gain, envelope and
    fades, in the source's channels and before pan. None when it is silent there."""
    lo = max(first, clip.heard_start)
    hi = min(first + count, clip.heard_end)
    if hi <= lo:
        return None
    n = hi - lo
    src = clip.offset + (lo - clip.start)
    audio = store.read(clip.media, src, n).astype(np.float64)
    t = np.arange(lo, hi, dtype=np.float64)  # timeline frames

    g = np.full(n, curves.gain(clip.gain_db), dtype=np.float64)
    env = curves.db_curve(clip.envelope, src, n)
    if env is not None:
        g *= curves.gain(env)
    # A stored fade and a derived mute ramp share the edge: the longer wins,
    # so projects that stored the old 30 ms fade render as before.
    fade_in = max(clip.fade_in, ramps[0])
    fade_out = max(clip.fade_out, ramps[1])
    if clip.xfade_in:
        g *= _ramp(t, clip.heard_start, clip.xfade_in)
    elif fade_in and lo < clip.start + fade_in:
        g *= _ramp(t, clip.start, fade_in)
    if clip.xfade_out:
        g *= _ramp(-t, -clip.heard_end, clip.xfade_out)
    elif fade_out and hi > clip.end - fade_out:
        # The last frame of the clip is end-1: it plays at gain 0 only past it.
        g *= _ramp(-t, -(clip.end - 1), fade_out)
    return lo, hi, audio * g


def downmix(audio: np.ndarray) -> np.ndarray:
    """``(channels, n)`` to ``(1, n)`` as (L+R)/2: a centred voice keeps its level."""
    return audio.mean(axis=0, keepdims=True) if audio.shape[0] > 1 else audio


def _clip_into(out: np.ndarray, clip: Clip, store: Store, first: int, count: int,
               ramps: tuple[int, int] = (0, 0), mono: bool = False) -> None:
    signal = _clip_signal(clip, store, first, count, ramps)
    if signal is None:
        return
    lo, hi, audio = signal
    if mono:
        audio = downmix(audio)
    n, a = hi - lo, lo - first
    if audio.shape[0] == 1:
        left_g, right_g = pan_gains(clip.pan * 100.0, "power")
        mono = audio[0]
        out[0, a:a + n] += mono * left_g
        out[1, a:a + n] += mono * right_g
    else:
        left_g, right_g = pan_gains(clip.pan * 100.0, "balance")
        out[0, a:a + n] += audio[0] * left_g
        out[1, a:a + n] += audio[1] * right_g


def _balance(buf: np.ndarray, pan: float) -> None:
    if pan:
        left_g, right_g = pan_gains(pan * 100.0, "balance")
        buf[0] *= left_g
        buf[1] *= right_g


def _track(track: Track, store: Store, first: int, count: int,
           rate: int) -> np.ndarray | None:
    clips = [c for c in track.clips
             if not c.muted and c.start < first + count and c.end > first]
    # Counted for the performance report: this scan visits every clip of the track in
    # every block, so it grows with the length of the project.
    perf.COUNTERS.note("mixer.clips_scanned", len(track.clips))
    if not clips:
        return None
    perf.COUNTERS.note("mixer.clips_mixed", len(clips))
    buf = np.zeros((2, count), dtype=np.float64)
    ramps = _mute_ramps(track, rate)
    for clip in clips:
        _clip_into(buf, clip, store, first, count, ramps.get(clip.id, (0, 0)), track.mono)
    gate = _gate_gain(track.gate, first, count, rate)
    if gate is not None:
        buf *= gate
    g = curves.gain(track.gain_db)
    auto = curves.db_curve(track.automation, first, count)
    buf *= g if auto is None else g * curves.gain(auto)
    _balance(buf, track.pan)
    return buf


def mix(project: Project, store: Store, first: int, count: int) -> np.ndarray:
    """Stereo float32 ``(2, count)`` for timeline frames ``[first, first+count)``."""
    master = np.zeros((2, count), dtype=np.float64)
    buses = {b.id: np.zeros((2, count), dtype=np.float64) for b in project.buses}
    # Solo overrides mute: while anything is soloed, only soloed tracks are
    # heard, muted or not. A muted bus still silences its tracks.
    soloing = any(t.solo for t in project.tracks)
    for track in project.tracks:
        audible = track.solo if soloing else not track.mute
        if not audible:
            continue
        buf = _track(track, store, first, count, project.rate)
        if buf is not None:
            target = buses.get(track.bus, master)
            target[:] += buf
    for bus in project.buses:
        if bus.mute:
            continue
        buf = buses[bus.id]
        buf *= curves.gain(bus.gain_db)
        _balance(buf, bus.pan)
        master += buf
    master *= curves.gain(project.master_gain_db)
    return master.astype(np.float32)


def track_stem(track: Track, store: Store, first: int, count: int, channels: int,
               *, as_heard: bool, rate: int, track_gain: bool = False) -> np.ndarray:
    """One track on its own, for stem export: ``(channels, count)`` float32.

    The edit is applied (cuts, crossfades, clip gain, envelopes, fades; muted
    clips are silence, and so is the track's gate, with its edge ramps).
    ``as_heard`` adds the track's own gain and automation (the ducking);
    ``track_gain`` adds only the gain (the automixer's music stems). Pan
    is left out either way: the stem keeps its channels, a mono track stays
    mono, and placing it is the mixing console's job. Buses and the master are
    never applied. Solo and mute are the caller's business.
    """
    buf = np.zeros((channels, count), dtype=np.float64)
    ramps = _mute_ramps(track, rate)
    for clip in track.clips:
        if clip.muted:
            continue
        signal = _clip_signal(clip, store, first, count, ramps.get(clip.id, (0, 0)))
        if signal is None:
            continue
        lo, hi, audio = signal
        if track.mono:
            audio = downmix(audio)
        if audio.shape[0] < channels:  # a mono clip on a stereo track
            audio = np.repeat(audio[:1], channels, axis=0)
        buf[:, lo - first:hi - first] += audio[:channels]
    gate = _gate_gain(track.gate, first, count, rate)
    if gate is not None:
        buf *= gate
    if as_heard:
        auto = curves.db_curve(track.automation, first, count)
        g = curves.gain(track.gain_db)
        buf *= g if auto is None else g * curves.gain(auto)
    elif track_gain:
        buf *= curves.gain(track.gain_db)
    return buf.astype(np.float32)
