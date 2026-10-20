"""Playback: the project's mix to the audio device, block by block (WP2).

One ``sounddevice.OutputStream`` (PortAudio: CoreAudio on a Mac, WASAPI on
Windows) asks for a block of audio every ~21 ms. The callback mixes it with
``mixer.mix``, the same function the exporter uses, so what you hear is
what you export (``tests/golden/`` pins that down for any engine).

**The door to a native engine stays open.** Nothing outside this module may
assume playback is done in Python. The public surface is plain data in and
out: ``set_project``, ``play``, ``stop``, ``seek``, ``scrub``, ``status``,
``levels`` and ``close``. If Python fails on glitches or latency, a JUCE
extension replaces this class behind the same surface (docs/PLAN.md, WP2).

**The audio thread never waits.** The callback never takes ``session.lock``:
the project reaches it by ``set_project`` (a session subscriber), a plain
attribute assignment. The only lock it touches, ``_tlock``, guards a handful
of transport numbers and is never held for more than a few assignments.
Decoding ahead is done by the helper thread (prefetch), not the callback.

**Display follows the ear.** ``status()["position"]`` is the frame being
*heard*: what was rendered, minus what is still queued in the resampler and
in the device (``stream.latency``). The playhead, transcript highlight and
meters use it, so they do not run 20-45 ms ahead of the sound. It comes
with ``t``, the monotonic time it is heard at (the callback that produced it,
or later when the run's first frames are still in the device), and ``seq``,
which changes with every transport change: the browser extrapolates the
playhead from that anchor every animation frame (``ui/playhead-clock.js``).

**Stop means silence now.** Stopping, or jumping elsewhere while playing,
aborts the stream so what the device has queued (a block plus the device's
own lead, about 36 ms) is never heard, and starts it again for the next play
(``_park``/``_wake``; starting a parked stream costs 4-10 ms, opening one far
more). ``docs/PLAYBACK-LATENCY.md`` has the measurements.

**Fail soft** (ground rule 13). The callback catches everything: a failing
block plays silence and is counted. A media chunk that cannot be decoded
plays silence for that stretch and marks the media damaged; the rest of the
file plays. The helper thread (every 250 ms) turns those into notices, and
handles what the callback cannot: a stream that died or stalled (device
unplugged, Bluetooth dropped, default output switched) is reopened on the
current default device, and late blocks raise the buffer to 2048 frames and
say "playback is struggling" instead of stuttering silently. A device that
cannot run the project rate gets resampled output (soxr).

**Skips and tape rate** (WP18, WP26). ``play(at, until, rate=, skip=)``
builds a ``PlayPlan`` on the control side: the programme's played stretches
with the skipped ranges left out and crossfaded joins (``playplan.py``). The
callback reads that played timeline forwards, or backwards for a negative
rate, and a speed other than 1 goes through the same soxr stream that
handles the device rate, now at ``|rate| x project rate`` in: tape-style,
the pitch follows the speed. The playhead is mapped back to programme
frames, so it jumps over a skip and runs at the speed. Fast listening with
the pitch kept (WP26) does not go through soxr: ``stretch.Stretcher`` (WSOLA)
pulls the played timeline a hop at a time in the callback, at a speed that
``set_rate`` can change at any moment, and the playhead advances by the speed
heard. It costs about what a block of plain playback costs (see
``tests/test_engine_stretch.py``).
"""

from __future__ import annotations

import gc
import logging
import math
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import numpy as np
import sounddevice as sd
import soxr

from . import diag, latency, meter, preview_level
from .media import CHUNK_SEC
from .messages import KuulasError, t
from .model import Project
from .perf import COUNTERS
from .playplan import (
    XFADE_S,
    PlaybackRequestError,
    PlayPlan,
    check_loop,
    normalise_skip,
)
from .stretch import MAX_RATE as MAX_STRETCH
from .stretch import MIN_RATE as MIN_STRETCH
from .stretch import Stretcher

log = logging.getLogger("kuulas.engine")

#: Block timings for the performance report (perf.py): a dict lookup, no lock.
_note = COUNTERS.note

#: Frames per block: about 21 ms at 48 kHz, the plan's default.
BLOCKSIZE = 1024
#: The buffer late blocks raise it to (about 43 ms). WP23a will also use it
#: when the CPU meter shows sustained load over 60 %.
SAFE_BLOCKSIZE = 2048
#: The PortAudio latency asked for, and what late blocks raise it to (with
#: ``SAFE_BLOCKSIZE``). On Core Audio the block size sets the buffer and the two
#: give the same figures (measured 2026-10-20: 34.8 ms at 1024 frames, 56.7 ms
#: at 2048, either way); other host APIs size their buffers by it.
LATENCY = "low"
SAFE_LATENCY = "high"
#: A play or seek while playing that lands further than this from the heard
#: frame drops the queued audio (the stream is aborted and started again).
#: Nearer (a nudge, a J/K/L speed change in place) it plays on: the abort
#: blocks for about 100 ms in PortAudio's Core Audio code, and a gap that long
#: is worse than 36 ms of audio from nearly the same place.
JUMP_FLUSH_S = 0.05
#: The helper thread's period: prefetch, watchdog, device checks, notices.
TICK_S = 0.25
#: How far ahead the helper thread decodes media.
PREFETCH_S = 5.0
#: What must be read ahead before a play, seek or loop change takes effect, so
#: the first blocks find their audio cached (the rest follows on the next tick).
WARM_S = 2.0
#: Python's thread switch interval while the stream is open. The default 5 ms
#: is how long the audio callback may wait for the GIL each time another
#: thread (the web server, the helper) holds it; 0.5 ms makes the wait short.
SWITCH_S = 0.0005
#: A read-ahead chunk nobody wants any more is dropped after this long (a seek
#: warms new chunks just before the helper's next tick counts them as wanted).
KEEP_S = 3.0
#: A callback that has not run for this long while playing is a dead stream.
WATCHDOG_S = 1.0
#: This many late blocks within ``LATE_WINDOW_S`` count as struggling. One
#: underflow on its own happens (a stream starting, a page fault) and is
#: only counted.
LATE_COUNT = 2
LATE_WINDOW_S = 5.0
#: An idle stream is closed after this long, so the next play opens the
#: device that is the default then (PortAudio's device list is read again).
IDLE_CLOSE_S = 30.0
#: How much a scrub plays from the frame: a short burst, about 60 ms.
#: WP26 (scrubbing) refines this.
SCRUB_S = 0.06
#: Notices kept for the UI.
MAX_NOTICES = 20
#: Tape-rate speeds: the JKL ladder's slowest (held K + L, 0.25x) to its
#: fastest (5x), either direction.
MIN_SPEED = 0.25
MAX_SPEED = 5.0
#: How many times a loop change looks for a wrap the audio thread has not
#: reached yet before it restarts the run instead (it only loses a race with
#: a callback that runs between two of its own steps).
SPLICE_TRIES = 4
#: A frame past any project, for keeping a skip list unclipped.
_FAR = 2**62
#: "No resampler made for this speed" (None means none is needed).
_MISSING = object()


class EngineError(KuulasError):
    """Playback could not start: no device, or the device refused to open."""


class _Run:
    """One play's fixed parameters. Replaced as a whole under ``_tlock``, so
    the audio thread reads one consistent reference per block."""

    __slots__ = ("loop", "plan", "skip", "speed", "stretch")

    def __init__(self, plan: PlayPlan, speed: float, skip: tuple[tuple[int, int], ...],
                 loop: tuple[int, int] | None = None, stretch: bool = False):
        self.plan, self.speed, self.skip, self.loop = plan, speed, skip, loop
        #: Played with the pitch kept (WSOLA), at the engine's live rate.
        self.stretch = stretch


def _check_speed(rate: object, preserve_pitch: bool) -> float:
    try:
        speed = float(rate)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise PlaybackRequestError("error.engine.bad_speed", speed=str(rate)) from None
    if not math.isfinite(speed):
        raise PlaybackRequestError("error.engine.bad_speed", speed=str(rate))
    if preserve_pitch and abs(speed) != 1.0:
        # Pitch kept (fast listening, stepless): forward only, in the range
        # the stretcher handles. Backward at other speeds would be chipmunk
        # speech played in reverse; refused rather than silently wrong.
        if speed < 0 or not MIN_STRETCH <= speed <= MAX_STRETCH:
            raise PlaybackRequestError("error.engine.stretch_unavailable",
                                       speed=str(rate))
        return speed
    if not MIN_SPEED <= abs(speed) <= MAX_SPEED:
        raise PlaybackRequestError("error.engine.bad_speed", speed=str(rate))
    return speed


def _clock_text(frame: int, rate: int) -> str:
    seconds = max(0, frame) // rate
    return f"{seconds // 60}:{seconds % 60:02d}"


class _SafeStore:
    """The media store as the audio thread sees it: a read never raises.

    A read that fails is retried one decode chunk at a time, so only the
    chunk that is broken plays silence; that chunk is remembered and not
    tried again (decoding a broken chunk on every block would itself make
    playback late). Each newly damaged chunk is queued as an event for the
    helper thread to log and show.
    """

    def __init__(self, store, rate: int, events: deque):
        self.store = store
        self.step = CHUNK_SEC * rate
        self.events = events
        #: diag.Probe when --debug is on, else None
        self.probe: diag.Probe | None = None
        #: media id -> indices of chunks that failed to decode
        self.damaged: dict[str, set[int]] = {}
        #: The read-ahead: (media id, chunk index) -> (whole chunk, last time
        #: wanted). Written by the helper and control threads, read by the
        #: audio thread with plain dict get/set/pop (atomic), so no lock.
        self.cache: dict[tuple[str, int], tuple[np.ndarray, float]] = {}
        #: media id -> channel count of its cached chunks
        self.channels: dict[str, int] = {}
        #: reads that found nothing cached (audio thread writes)
        self.misses = 0

    def read(self, media_id: str, first: int, count: int) -> np.ndarray:
        """The audio thread's read: copies from the read-ahead cache and never
        touches the disk. What is not cached plays as silence and is counted
        as a miss (the helper thread was late, or the source is new)."""
        probe = self.probe
        if probe is None:
            return self._cached(media_id, first, count)
        began = time.perf_counter()
        try:
            return self._cached(media_id, first, count)
        finally:
            probe.mixer_read(time.perf_counter() - began, media_id)

    def _cached(self, media_id: str, first: int, count: int) -> np.ndarray:
        step, cache = self.step, self.cache
        pieces: list[tuple[int, np.ndarray]] = []
        pos, end, missed = max(first, 0), first + count, False
        while pos < end:
            index = pos // step
            n = min(end, (index + 1) * step) - pos
            hit = cache.get((media_id, index))
            if hit is None:
                missed = True
            else:
                a = pos - index * step
                pieces.append((pos - first, hit[0][:, a:a + n]))
            pos += n
        channels = max((d.shape[0] for _, d in pieces),
                       default=self.channels.get(media_id, 1))
        out = np.zeros((channels, count), dtype=np.float32)
        for at, data in pieces:
            out[:, at:at + data.shape[1]] = data
        if missed:
            self.misses += 1
            if self.probe is not None:
                self.probe.miss(media_id)
        return out

    def fill(self, media_id: str, index: int, now: float) -> None:
        """The helper thread's read: decode chunk ``index`` into the cache
        (once; a chunk already there just has its time refreshed). Only the
        helper and the control side call this, never the audio thread."""
        key = (media_id, index)
        hit = self.cache.get(key)
        if hit is not None:
            self.cache[key] = (hit[0], now)
            return
        probe = self.probe
        began = time.perf_counter()
        data = self._read(media_id, index * self.step, self.step)
        if probe is not None:
            probe.prefetch_read(time.perf_counter() - began, media_id)
        self.channels[media_id] = data.shape[0]
        self.cache[key] = (data, now)

    def evict(self, wanted: set[tuple[str, int]], now: float) -> None:
        """Drop chunks that are not wanted and have not been for ``KEEP_S``."""
        for key, (_, stamp) in list(self.cache.items()):
            if key not in wanted and now - stamp > KEEP_S:
                self.cache.pop(key, None)

    def _read(self, media_id: str, first: int, count: int) -> np.ndarray:
        if not self.damaged.get(media_id):
            try:
                return self.store.read(media_id, first, count)
            except Exception:  # noqa: BLE001 - any decode error costs that chunk only
                log.debug("read of %s failed; retrying chunk by chunk", media_id)
        return self._piecewise(media_id, first, count)

    def _piecewise(self, media_id: str, first: int, count: int) -> np.ndarray:
        pieces: list[tuple[int, np.ndarray | None]] = []
        pos, end = first, first + count
        while pos < end:
            index = pos // self.step
            n = min(end, (index + 1) * self.step) - pos
            data = None
            if index not in self.damaged.get(media_id, ()):
                try:
                    data = self.store.read(media_id, pos, n)
                except Exception as exc:  # noqa: BLE001 - see the class docstring
                    self.damaged.setdefault(media_id, set()).add(index)
                    self.events.append(("damaged", media_id, index, repr(exc)))
            pieces.append((n, data))
            pos += n
        # With nothing decoded the channel count is unknown; mono silence
        # mixes as silence all the same.
        channels = max((d.shape[0] for _, d in pieces if d is not None), default=1)
        out = np.zeros((channels, count), dtype=np.float32)
        at = 0
        for n, data in pieces:
            if data is not None:
                out[:, at:at + n] = data
            at += n
        return out


class Engine:
    """Plays one session's project. See the module docstring.

    ``clock`` and ``background`` are for tests: a fake clock, and no helper
    thread (the test calls ``_tick`` itself).
    """

    def __init__(self, session, blocksize: int = BLOCKSIZE, device=None, *,
                 clock: Callable[[], float] = time.monotonic,
                 background: bool = True, debug: bool | None = None):
        self._session = session
        self._project: Project = session.state
        #: Previewing a temporary project (``play_preview``): the real
        #: project to go back to, where the playhead was, and whether it is on.
        self._preview = False
        self._preview_limit = False  # the safety limiter, on a preview only (WP82)
        self._base: Project = session.state
        self._preview_anchor = 0
        self.rate = self._project.rate
        self._blocksize = int(blocksize)
        self._device = device
        self._clock = clock
        self._background = background

        #: Events from the audio thread, read by the helper thread. A deque's
        #: append and popleft are atomic, so neither side waits.
        self._events: deque = deque(maxlen=1000)
        self._store = _SafeStore(session.store, self.rate, self._events)
        #: --debug: timings of the callback and the media reads (diag.py)
        self._probe = diag.Probe() if (diag.enabled() if debug is None else debug) \
            else None
        self._store.probe = self._probe
        self._report_cursor = (0, 0, 0, 0)
        self._reporter: threading.Thread | None = None

        # Transport, shared with the audio thread under _tlock (held only for
        # a few assignments). A seek or play starts a new "run": _gen counts
        # them, _anchor is where it started (programme frame), _run its plan,
        # speed and skip list, _fed the next frame of its played timeline to
        # mix, _out how many device frames have been played since the anchor.
        self._tlock = threading.Lock()
        self._playing = False
        self._until: int | None = None
        self._anchor = 0
        self._run: _Run | None = None
        self._fed = 0
        self._out = 0
        self._gen = 0
        #: Programme frames heard so far in a pitch-kept run (float: the
        #: speed is stepless, so this is not ``_out`` times a constant).
        self._acc = 0.0
        #: The live speed of a pitch-kept run, changed by ``set_rate`` while
        #: it plays; the audio thread hands it to the stretcher every hop.
        self._stretch_rate = 1.0
        self._stretcher: Stretcher | None = None
        self._stretcher_gen = -1
        self._hop_frames = 0

        # Audio-thread state: the queue between mixer and device. Only the
        # callback touches these, or the control side while no stream runs.
        self._fifo = np.zeros((0, 2), dtype=np.float32)
        self._fifo_gen = -1
        self._flushed = False
        #: |speed| -> the soxr stream from |speed| x project rate to the
        #: device rate, or None when the two are equal. Made on the control
        #: side (never in the callback), anew whenever a stream is opened.
        self._resamplers: dict[float, soxr.ResampleStream | None] = {}
        #: (run, first played frame, count, peak left, peak right) of
        #: recent mixed blocks
        self._recent: deque = deque(maxlen=64)

        #: The level meter. The callback keeps the loudest peak per channel (linear)
        #: since the last ``meter()`` and the mean square of its latest block;
        #: ``meter()`` reads and clears them. Plain tuples, replaced whole: an update
        #: lost to the race between the two threads costs one block of a display,
        #: never a lock in the callback.
        self._m_peak = (0.0, 0.0)
        self._m_ms = (0.0, 0.0)
        self._hold_l = meter.PeakHold()
        self._hold_r = meter.PeakHold()

        # Counters and timestamps the audio thread writes.
        self._failed = 0
        self._late = 0
        self._late_times: deque = deque(maxlen=64)
        self._last_callback = clock()
        #: The latency numbers (latency.py): when the recent callbacks ran, and
        #: how far ahead of each its first frame reached the converter.
        self._cb_times: deque = deque(maxlen=128)
        self._dac_leads: deque = deque(maxlen=128)
        #: The transport's version: changes with every play, seek, stop, speed
        #: change and run that ends by itself (the browser drops older anchors).
        self._seq = 0
        #: When the frames counted in ``_out`` were last brought up to date (the
        #: callback that rendered them, or the start of the run).
        self._out_at = clock()

        # Control side (API threads and the helper thread), under _ctl.
        self._ctl = threading.RLock()
        self._stream = None
        self._device_name = ""
        self._dev_rate = self.rate
        self._latency_frames = 0
        self._latency_setting = LATENCY
        self._stream_latency = 0.0
        #: Stopped by ``_park`` (aborted on purpose, kept for the next play), and
        #: how many finished callbacks our aborts still owe.
        self._parked = False
        self._aborts_pending = 0
        self._expect_finish = False
        self._died = False
        self._last_active = clock()
        self._last_escalation = -math.inf
        self._notices: deque = deque(maxlen=MAX_NOTICES)
        self._notice_id = 0
        self._closed = False
        self._halt = threading.Event()
        self._thread: threading.Thread | None = None
        #: the switch interval before ours (None: not changed)
        self._saved_switch: float | None = None
        self._gc_frozen = False

        session.subscribe(self.set_project)

    # -- public surface ------------------------------------------------------

    def set_project(self, project: Project) -> None:
        """The project to play from the next block on. Called by the session
        after every change; one attribute assignment, so the audio thread
        never sees half a project. During a preview the real project is only
        remembered, and comes back when the preview ends."""
        if self._preview:
            self._base = project
        else:
            self._project = project

    def play_preview(self, project: Project, until: int | None = None,
                     limit: bool = False) -> None:
        """Play a temporary ``project`` from its start (a clipboard entry,
        WP46) without touching the real one. The playhead is put back where it
        was when the preview ends: by ``stop``, ``seek``, ``play`` or running
        out. Edits made meanwhile are kept for then. ``limit`` puts the safety
        limiter on this preview's output only (WP82)."""
        with self._ctl:
            self._end_preview()
            self._preview_limit = limit
            with self._tlock:
                self._preview_anchor = self._heard() if self._playing else self._anchor
            self._base = self._project
            self._project = project
            self._preview = True
            try:
                self._play(0, until)
            except BaseException:
                self._end_preview()
                raise

    def _end_preview(self) -> None:
        """Back to the real project and the playhead as it was; silent."""
        with self._ctl:
            if not self._preview:
                return
            with self._tlock:
                self._playing = False
                self._project = self._base
                self._preview = False
                self._start_run(self._preview_anchor)

    def play(self, at: int | None = None, until: int | None = None, *,
             rate: float = 1.0, preserve_pitch: bool = True,
             skip=None, loop=None) -> None:
        """Play the real project (ending a preview first); see ``_play``."""
        self._end_preview()
        self._play(at, until, rate=rate, preserve_pitch=preserve_pitch,
                   skip=skip, loop=loop)

    def _play(self, at: int | None = None, until: int | None = None, *,
              rate: float = 1.0, preserve_pitch: bool = True,
              skip=None, loop=None) -> None:
        """Play from ``at`` (default: where the playhead is) to ``until``
        (default: the end of the project; below ``at`` when ``rate`` is
        negative, default the start).

        ``loop``: a ``(start, end)`` pair of frames. Playing runs to ``end``
        and wraps back to ``start`` with the crossfade of a skip, for ever
        (``until`` is then not used), respecting ``skip``. The end is cut at
        the project's end. Called while playing from where it is, with
        another loop or none, it takes effect at the next wrap, never
        mid-block: with none, playing goes on past the loop's end. Loops
        play forward only. ``status()["loop"]`` reports the loop.

        ``skip``: frame ranges ``(a, b)`` to jump over, crossfaded; empty or
        None plays everything. ``rate``: tape speed, ``MIN_SPEED`` to
        ``MAX_SPEED`` either way (negative is backward); with
        ``preserve_pitch`` (the default) 1 and -1 are tape-exact and any other
        forward speed from 0.5 to 3 is time-stretched with the pitch kept
        (``stretch.py``, WSOLA; ``set_rate`` changes it while playing). A bad
        ``rate`` or ``skip`` raises ``PlaybackRequestError``, no device
        ``EngineError``; nothing changes then."""
        speed = _check_speed(rate, preserve_pitch)
        stretch = preserve_pitch and speed not in {1.0, -1.0}
        skip_list = normalise_skip(skip, 0, _FAR)
        loop_range = self._check_loop(loop, skip_list, speed)
        with self._ctl:
            self._wake()  # stopped by us: start again (cheap), or closed if it will not
            if self._stream is not None and (self._died or not self._stream.active):
                self._close_stream()  # died since the last tick: open afresh
            if self._stream is None:
                self._open(refresh=True)
            self._resampler_for(1.0 if stretch else abs(speed))
            with self._tlock:
                gen, run = self._gen, self._run
                continuing = at is None and self._playing
                heard = self._heard() if self._playing else None
                if continuing:
                    start = self._heard()
                else:
                    start = self._anchor if at is None else max(0, int(at))
                jump = heard is not None and abs(start - heard) > JUMP_FLUSH_S * self.rate
                # Same speed (forward) and skip list, only a new end: the
                # run goes on with nothing re-queued, as before skips.
                same = (continuing and run is not None and speed > 0
                        and run.stretch == stretch
                        and (stretch or run.speed == speed) and run.skip == skip_list)
                keep = same and run.loop is None and loop_range is None
                splice = same and run.loop is not None and self._fed > 0
                lo = self._anchor if keep else start
            if loop_range is not None:  # the wrap must find the loop's start cached
                self._fill_windows([(loop_range[0], loop_range[0] + self._ahead(
                    WARM_S, speed))])
            if splice and (loop_range == run.loop or self._splice(
                    run, gen, loop_range, until, skip_list)):
                self._last_active = self._clock()
                self._last_callback = self._clock()
                return
            new = _Run(self._plan(lo, until, speed, skip_list, loop_range), speed,
                       skip_list, loop_range, stretch)
            if stretch:
                self._stretch_rate = speed
            if not self._gc_frozen:
                # Everything built so far (the app, the project) is long-lived:
                # out of the collector's sight, a full collection during
                # playback has far less to walk.
                gc.freeze()
                self._gc_frozen = True
            if not keep:  # the first blocks must find their audio cached
                self._read_ahead(new, 0, WARM_S, evict=False)
            flush = jump and not keep
            if flush:  # what the device queued from the old place must not be heard
                self._park()
            with self._tlock:
                if keep and self._gen == gen and self._playing:
                    self._run = new
                    self._seq += 1
                else:
                    self._start_run(start, new)
                self._until = until
                self._playing = True
            if flush:
                self._wake()
                if self._stream is None:
                    self._open_or_pause()
            self._last_active = self._clock()
            self._last_callback = self._clock()
            self._start_thread()

    def set_rate(self, rate: float) -> bool:
        """Change the speed of a pitch-kept run that is playing, stepless and
        without a click (the stretcher takes the new speed at its next hop,
        about 20 ms). False, and nothing changed, if no such run is playing:
        the caller then starts one with ``play``."""
        speed = _check_speed(rate, True)
        with self._tlock:
            run = self._run
            if not (self._playing and run is not None and run.stretch):
                return False
            self._stretch_rate = speed
            self._seq += 1
        return True

    @property
    def is_playing(self) -> bool:
        """Whether audio plays, for the playback gate (``priority.GATE``): one
        attribute read, no ``_tlock``, so background threads that poll it never
        contend with the audio callback."""
        return self._playing

    def stop(self) -> None:
        """Stop where the sound was: the playhead stays at the heard frame
        (after a preview: where it was before it), and nothing the device
        still had queued is heard (``_park``)."""
        with self._ctl:
            with self._tlock:
                was = self._playing
            self._end_preview()
            with self._tlock:
                if self._playing:
                    self._start_run(self._heard())
                    self._playing = False
                self._last_active = self._clock()
            if was:
                self._park()

    def seek(self, frame: int) -> None:
        """Move the playhead; playback, if on, continues from there at the
        same speed, still skipping the same ranges."""
        self._end_preview()
        frame = max(0, int(frame))
        with self._tlock:
            run, until = self._run, self._until
        new = None if run is None else _Run(
            self._plan(frame, until, run.speed, run.skip, run.loop), run.speed,
            run.skip, run.loop, run.stretch)
        if new is not None:
            self._read_ahead(new, 0, WARM_S, evict=False)
        with self._ctl:
            with self._tlock:
                far = JUMP_FLUSH_S * self.rate
                jump = self._playing and abs(frame - self._heard()) > far
            if jump:  # the old place's queued audio must not be heard
                self._park()
            with self._tlock:
                self._start_run(frame, new)
            if jump:
                self._wake()
                if self._stream is None:
                    self._open_or_pause()

    def scrub(self, frame: int) -> None:
        """Let the user hear where ``frame`` is: while playing, a seek; when
        stopped, a short burst from the frame. WP26 builds real scrubbing."""
        with self._tlock:
            playing = self._playing
        if playing:
            self.seek(frame)
        else:
            frame = max(0, int(frame))
            self.play(frame, frame + round(SCRUB_S * self.rate))

    def status(self) -> dict[str, Any]:
        """The transport, device and counters, and the notices. With
        ``--debug`` also ``"debug"`` (absent otherwise): timings over the last
        ~500 callbacks, in milliseconds: ``block_ms`` (what a block lasts),
        ``callbacks``, ``cb_avg_ms``/``cb_max_ms`` (whole callback),
        ``reads_avg_ms``/``reads_max_ms`` (the mixer waiting for media),
        ``mix_avg_ms``/``mix_max_ms`` (mixing and resampling without the
        reads), ``prefetch_reads``/``prefetch_ms``/``prefetch_max_ms`` (the
        helper thread's reads), ``slowest_reads`` (``[{name, ms}]``, three,
        mixer and prefetch together), ``slow`` (``reads``, ``mix``, ``other``
        or None when the worst callback fit in a block), and the status
        fields ``late_blocks``, ``failed_blocks``, ``device``,
        ``device_rate``, ``resampling``."""
        with self._tlock:
            previewing, playing = self._preview, self._playing
        if previewing and not playing:
            self._end_preview()  # it ran out by itself
        with self._tlock:
            playing, until, run = self._playing, self._until, self._run
            position = self._heard() if playing else self._anchor
            heard_at = self._heard_at() if playing else self._clock()
            seq, length = self._seq, self._project.length
        live = run if playing and run is not None else None
        end = None
        if live is not None and live.loop is None:
            end = until if until is not None else (length if live.speed > 0 else 0)
        with self._ctl:
            debug = self._debug_numbers((0, 0, 0, 0))[0] if self._probe else None
            notices = [{"id": n["id"], "key": n["key"], "params": n["params"],
                        "text": t(n["key"], **n["params"])} for n in self._notices]
            out = {
                "playing": playing,
                "preview": self._preview,
                "position": int(position),
                "t": heard_at,
                "seq": seq,
                "end": end,
                "until": until,
                "speed": ((self._stretch_rate if live.stretch else live.speed)
                          if live else 1.0),
                "skip": [list(r) for r in live.skip] if live else [],
                "loop": list(live.loop) if live and live.loop else None,
                "rate": self.rate,
                "device": self._device_name,
                "device_rate": self._dev_rate,
                "resampling": self._dev_rate != self.rate,
                "blocksize": self._blocksize,
                "failed_blocks": self._failed,
                "late_blocks": self._late,
                "damaged": sorted(self._store.damaged),
                "notices": notices,
                "latency": latency.report(
                    setting=self._latency_setting, stream_latency_s=self._stream_latency,
                    blocksize=self._blocksize, device_rate=self._dev_rate,
                    callback_times=list(self._cb_times),
                    dac_leads=list(self._dac_leads)),
            }
            if debug is not None:
                debug["latency"] = out["latency"]
                out["debug"] = debug
            return out

    def levels(self) -> dict[str, Any]:
        """Peak level per channel (linear, 1.0 = full scale) of the block
        being heard now, for the meters."""
        with self._tlock:
            playing, run = self._playing, self._run
            position = self._heard() if playing else self._anchor
            played = self._played() if playing else -1
        peak = [0.0, 0.0]
        for owner, first, count, left, right in list(self._recent):
            if owner is run and first <= played < first + count:
                peak = [left, right]
        return {"position": int(position), "peak": peak}

    def close(self) -> None:
        with self._ctl:
            self._closed = True
            self._halt.set()
            with self._tlock:
                self._playing = False
            self._close_stream()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(2)

    # -- transport helpers (caller holds _tlock) -------------------------------

    def _start_run(self, frame: int, run: _Run | None = None) -> None:
        self._anchor = frame
        if run is not None:
            self._run = run
        self._fed = self._out = 0
        self._acc = 0.0
        self._gen += 1
        self._seq += 1
        self._out_at = self._clock()

    def _played_raw(self) -> tuple[float, float]:
        """Frames of the run's played timeline that have reached the ear (below
        zero: still on their way) and the played frames per second: device frames
        since the anchor, at |speed| x the project rate, minus the device's output
        latency (which holds that much more)."""
        run = self._run
        if run is not None and run.stretch:
            live = self._stretch_rate
            return self._acc - self._latency_frames * live, live * self.rate
        speed = abs(run.speed) if run is not None else 1.0
        played = self._out * speed * self.rate / self._dev_rate
        return played - self._latency_frames * speed, speed * self.rate

    def _played(self) -> int:
        return max(0, round(self._played_raw()[0]))

    def _heard_at(self) -> float:
        """When the heard frame was the one ``_heard`` says: the last update of
        the counters, or later if the run's first frame has not reached the ear
        yet (the browser then holds the playhead until it has)."""
        played, per_second = self._played_raw()
        if played >= 0 or per_second <= 0:
            return self._out_at
        return self._out_at - played / per_second

    def _heard(self) -> int:
        """The programme frame at the listener's ear: the played frame mapped
        through the run's plan (it jumps over skips, runs backwards for a
        negative speed)."""
        run = self._run
        if run is None:
            return self._anchor
        length = self._project.length
        if run.speed > 0:
            return run.plan.position(self._played(), length)
        return run.plan.position(max(0, run.plan.length(length) - self._played()), length)

    def _check_loop(self, loop: object, skip: tuple[tuple[int, int], ...],
                    speed: float) -> tuple[int, int] | None:
        """The loop as asked, cut at the project's end, or a refusal (nothing
        has changed yet): backward loops are not built."""
        if loop is None:
            return None
        rate = self.rate
        start, end = check_loop(loop, skip, rate)
        if speed < 0:
            raise PlaybackRequestError("error.engine.bad_loop", loop=str(loop)[:40])
        return check_loop((start, min(end, self._project.length)), skip, rate)

    def _splice(self, run: _Run, gen: int, loop: tuple[int, int] | None,
                until: int | None, skip: tuple[tuple[int, int], ...]) -> bool:
        """Change or end the loop of a running ``run`` at its next wrap: the
        new plan plays as the old one up to a wrap the audio thread has not
        started to mix, so what it has mixed stays true, and takes over
        there. False if the run changed meanwhile (the caller restarts)."""
        margin = 2 * round(XFADE_S * self.rate / 2)  # both crossfades, at most
        for _ in range(SPLICE_TRIES):
            with self._tlock:
                if gen != self._gen or self._run is not run or not self._playing:
                    return False
                fed = self._fed
            wrap = run.plan.wrap_at_or_after(fed + margin)
            length = self._project.length
            plan = run.plan.then(wrap, loop=loop, skip=skip,
                                 hi=length if until is None else int(until),
                                 open_end=until is None, capped=True)
            need = max(run.plan.wrap_half, plan.splice_half)
            with self._tlock:
                if gen != self._gen or self._run is not run or not self._playing:
                    return False
                if wrap - need >= self._fed:  # still ahead of the audio thread
                    self._run = _Run(plan, run.speed, skip, loop, run.stretch)
                    self._until = until
                    return True
        return False

    def _plan(self, start: int, until: int | None, speed: float,
              skip: tuple[tuple[int, int], ...],
              loop: tuple[int, int] | None = None) -> PlayPlan:
        """The plan for playing from ``start`` (control side, outside
        ``_tlock``: it computes the crossfade curves)."""
        length = self._project.length
        if loop is not None:
            # Endless: the lead-in to the loop's end, then the loop for ever.
            return PlayPlan(start, loop[1], skip, rate=self.rate, open_end=False,
                            loop=loop)
        if speed > 0:
            hi = length if until is None else int(until)
            # Forward, the end follows edits made while playing: the
            # project's end, or ``until`` if the project is shorter.
            return PlayPlan(start, hi, normalise_skip(skip, start, hi), rate=self.rate,
                            open_end=until is None, capped=True)
        # Backward the played timeline is read from its end, so it is fixed
        # when play starts.
        hi = min(start, length)
        lo = 0 if until is None else max(0, min(int(until), hi))
        return PlayPlan(lo, hi, normalise_skip(skip, lo, hi), rate=self.rate,
                        open_end=False, capped=False)

    def _resampler_for(self, speed: float) -> None:
        """Make the soxr stream for ``|speed|`` if it is needed and missing
        (control side: never allocate one in the callback)."""
        if speed in self._resamplers:
            return
        if speed == 1.0 and self._dev_rate == self.rate:
            self._resamplers[speed] = None
        else:
            self._resamplers[speed] = soxr.ResampleStream(
                speed * self.rate, self._dev_rate, 2, dtype="float32", quality="HQ")

    # -- the audio thread ------------------------------------------------------

    def _callback(self, outdata, frames, time_info, status) -> None:
        """PortAudio's callback. Never raises: a failing block is silence."""
        now = self._clock()
        self._last_callback = now
        self._cb_times.append(now)
        probe = self._probe
        try:
            lead = latency.dac_lead(time_info)
            if lead is not None:
                self._dac_leads.append(lead)
            if status.output_underflow:
                self._late += 1
                self._late_times.append(now)
            began = time.perf_counter()
            cpu = time.thread_time() if probe is not None else 0.0
            if probe is not None:
                probe.acc = 0.0
            block = self._render(frames, now)
            rendered = time.perf_counter()
            outdata[:] = block
            self._measure(block)
            ended = time.perf_counter()
            _note("engine.callback_ms", (ended - began) * 1000.0)
            if probe is not None:
                total = ended - began
                probe.callback(total, probe.acc, rendered - began - probe.acc,
                               max(0.0, total - (time.thread_time() - cpu)))
            if ended - began > frames / self._dev_rate:
                self._late += 1
                self._late_times.append(now)
        except Exception as exc:  # noqa: BLE001 - the audio callback never raises
            outdata.fill(0)
            self._failed += 1
            self._events.append(("failed", repr(exc)))

    def _measure(self, block: np.ndarray) -> None:
        """Peak and mean square of the block just handed to the device (the meter).
        A bug here must cost the meter, not the sound, so it has its own guard."""
        try:
            peak_l, peak_r, ms_l, ms_r = meter.block_levels(block)
            held_l, held_r = self._m_peak
            self._m_peak = (max(held_l, peak_l), max(held_r, peak_r))
            self._m_ms = (ms_l, ms_r)
        except Exception as exc:  # noqa: BLE001 - the audio callback never raises
            self._events.append(("failed", f"meter: {exc!r}"))

    def meter(self) -> dict[str, float]:
        """What the live meter shows, dBFS: ``l``/``r`` the loudest peak since the last
        call, ``rms_l``/``rms_r`` the RMS level of the latest block, ``hold_l``/``hold_r``
        the peak-hold ticks (they fall; see ``meter.PeakHold``). Stopped: all at the
        floor, holds cleared. Cheap and lock-free; the live channel calls it about 15
        times a second."""
        peaks, self._m_peak = self._m_peak, (0.0, 0.0)
        if not self._playing:
            self._hold_l.reset()
            self._hold_r.reset()
            return {"l": meter.FLOOR_DB, "r": meter.FLOOR_DB, "rms_l": meter.FLOOR_DB,
                    "rms_r": meter.FLOOR_DB, "hold_l": meter.FLOOR_DB,
                    "hold_r": meter.FLOOR_DB}
        now = self._clock()
        left, right = meter.to_db(peaks[0]), meter.to_db(peaks[1])
        return {"l": left, "r": right,
                "rms_l": meter.to_db(math.sqrt(self._m_ms[0])),
                "rms_r": meter.to_db(math.sqrt(self._m_ms[1])),
                "hold_l": self._hold_l.update(left, now),
                "hold_r": self._hold_r.update(right, now)}

    def _render(self, frames: int, now: float | None = None) -> np.ndarray:
        """``(frames, 2)`` float32 at the device rate: the next block to play.
        ``now``: when the callback asking for it ran (the heard frame's time)."""
        out = np.zeros((frames, 2), dtype=np.float32)
        with self._tlock:
            playing, gen, fed, run = self._playing, self._gen, self._fed, self._run
        if not playing or run is None:
            return out
        project = self._project
        speed = 1.0 if run.stretch else abs(run.speed)  # stretched: resample 1:1
        resampler = self._resamplers.get(speed, _MISSING)
        if resampler is _MISSING:  # play() makes it first; a bug, not a device
            raise KeyError(speed)
        if gen != self._fifo_gen:
            self._fifo = np.zeros((0, 2), dtype=np.float32)
            self._flushed = False
            if resampler is not None:
                resampler.clear()
            self._fifo_gen = gen
        plan = run.plan
        end = plan.length(project.length)  # the played timeline's length
        ratio = speed * self.rate / self._dev_rate
        chunks = [self._fifo]
        have = len(self._fifo)
        stretcher = self._stretcher_for(gen, end) if run.stretch else None
        while have < frames and not self._flushed:
            if stretcher is not None:
                stretcher.set_speed(self._stretch_rate)
                hop = stretcher.next_hop()
                if hop is not None:
                    self._recent.append((run, int(stretcher.position), self._hop_frames,
                                         float(np.abs(hop[:, 0]).max()),
                                         float(np.abs(hop[:, 1]).max())))
                    y = hop if resampler is None else resampler.resample_chunk(hop)
                    chunks.append(y)
                    have += len(y)
                    fed = int(stretcher.position) + 2 * self._hop_frames
                if stretcher.finished:
                    if resampler is not None:
                        tail = resampler.resample_chunk(
                            np.zeros((0, 2), dtype=np.float32), last=True)
                        chunks.append(tail)
                        have += len(tail)
                    self._flushed = True
                continue
            # Always a whole block's worth of input: soxr gives no output for
            # a handful of input frames, and the loop then went round
            # hundreds of times mixing every track each time (measured: 489
            # mixes, 30 ms, in one block when scrubbing back at 5x). The
            # surplus waits in the queue for the next block.
            n = min(max(1, math.ceil(frames * ratio)), max(0, end - fed))
            if n > 0:
                mix_began = time.perf_counter()
                if run.speed > 0:
                    block = plan.read(project, self._store, fed, n)
                else:  # backward: the played timeline from its end
                    block = plan.read(project, self._store, end - fed - n, n)[:, ::-1]
                _note("engine.mix_ms", (time.perf_counter() - mix_began) * 1000.0)
                self._recent.append((run, fed, n, float(np.abs(block[0]).max()),
                                     float(np.abs(block[1]).max())))
                fed += n
                y = (block.T if resampler is None
                     else resampler.resample_chunk(np.ascontiguousarray(block.T)))
                chunks.append(y)
                have += len(y)
            if fed >= end:
                if resampler is not None:
                    tail = resampler.resample_chunk(
                        np.zeros((0, 2), dtype=np.float32), last=True)
                    chunks.append(tail)
                    have += len(tail)
                self._flushed = True
        queued = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        take = min(frames, len(queued))
        out[:take] = queued[:take]
        self._fifo = queued[take:]
        done = self._flushed and len(self._fifo) == 0
        with self._tlock:
            if gen == self._gen:  # no seek or stop meanwhile
                self._fed = fed
                self._out += take
                self._out_at = self._clock() if now is None else now
                if run.stretch:  # programme frames heard, at the live speed
                    self._acc += take * self._stretch_rate * self.rate / self._dev_rate
                if done:
                    self._playing = False
                    self._seq += 1
                    self._anchor = (plan.final(project.length) if run.speed > 0
                                    else plan.lo)
                    self._fed = self._out = 0
                    self._acc = 0.0
        if self._preview and self._preview_limit:
            out = preview_level.soft_limit(out)
        return out

    def _stretcher_for(self, gen: int, end: int) -> Stretcher:
        """The WSOLA stretcher of this run (audio thread): made at the run's
        first block, its input the run's played timeline mixed hop by hop."""
        if self._stretcher is None or self._stretcher_gen != gen:
            self._stretcher = Stretcher(self._stretch_fetch, end, self.rate,
                                        self._stretch_rate)
            self._stretcher_gen = gen
            self._hop_frames = self._stretcher.hop
        self._stretcher.length = end  # an edit while playing moves the end
        return self._stretcher

    def _stretch_fetch(self, first: int, count: int) -> np.ndarray:
        run = self._run
        if run is None:  # stopped between two hops: silence
            return np.zeros((2, count), dtype=np.float32)
        return run.plan.read(self._project, self._store, first, count)

    def _finished(self) -> None:
        """PortAudio's finished callback: the stream stopped. Unless we
        stopped it, the device went away."""
        if self._aborts_pending > 0:  # ``_park``'s abort (it may report late)
            self._aborts_pending -= 1
            return
        if not self._expect_finish:
            self._died = True

    def _park(self) -> None:
        """Abort the stream so nothing it has queued is heard; ``_wake`` starts
        it again. Caller holds ``_ctl`` and not ``_tlock`` (the abort waits for a
        running callback, which takes ``_tlock``). Measured on Core Audio
        (2026-10-20): the abort returns after about 105 ms (PortAudio polls the
        unit in 100 ms sleeps after stopping it; the sound ends at the stop),
        a start takes 4-10 ms."""
        stream = self._stream
        if stream is None or self._parked or not stream.active:
            return
        self._aborts_pending += 1
        try:
            stream.abort()
        except sd.PortAudioError as exc:
            self._aborts_pending -= 1
            log.warning(t("log.engine.abort_failed", error=str(exc)))
            return
        self._parked = True

    def _wake(self) -> None:
        """Start a parked stream again. One that will not start is closed, and
        the caller opens a new one."""
        stream = self._stream
        if stream is None or not self._parked:
            return
        self._parked = False
        self._died = False
        self._last_callback = self._clock()
        try:
            stream.start()
        except sd.PortAudioError as exc:
            log.warning(t("log.engine.start_failed", error=str(exc)))
            self._close_stream()

    def _open_or_pause(self) -> None:
        """Open a stream for a run already playing; with no device, pause and
        say so (the request that jumped has nothing to raise to)."""
        try:
            self._open(refresh=True)
        except EngineError as exc:
            with self._tlock:
                self._playing = False
                self._seq += 1
            self._notify(exc.key, **exc.params)
            log.warning(str(exc))

    # -- the stream (caller holds _ctl) ------------------------------------------

    def _refresh_devices(self) -> None:
        """Make PortAudio read the device list again, so a newly plugged or
        newly default device is seen. Only while no stream of ours is open
        (sounddevice documents ``_terminate``/``_initialize`` for this)."""
        try:
            sd._terminate()
            sd._initialize()
        except sd.PortAudioError as exc:
            log.warning(t("log.engine.refresh_failed", error=str(exc)))

    def _open(self, refresh: bool, device=None) -> None:
        """Open and start a stream on ``device`` (default: the engine's)."""
        if refresh:
            self._refresh_devices()
        device = self._device if device is None else device
        try:
            info = sd.query_devices(device, "output")
        except (sd.PortAudioError, ValueError):
            raise EngineError("error.engine.no_device") from None
        name = str(info.get("name", ""))
        own_rate = round(float(info.get("default_samplerate") or self.rate))
        kwargs = {"channels": 2, "dtype": "float32", "blocksize": self._blocksize,
                  "latency": self._latency_setting, "device": device,
                  "callback": self._callback,
                  "finished_callback": self._finished}
        try:
            stream = sd.OutputStream(samplerate=self.rate, **kwargs)
            dev_rate = self.rate
        except sd.PortAudioError as exc:
            if own_rate == self.rate:
                raise EngineError("error.engine.open_failed", device=name,
                                  error=str(exc)) from None
            try:
                stream = sd.OutputStream(samplerate=own_rate, **kwargs)
            except sd.PortAudioError as again:
                raise EngineError("error.engine.open_failed", device=name,
                                  error=str(again)) from None
            dev_rate = own_rate
        self._dev_rate = dev_rate
        # Every speed's resampler ends at the device rate: make them afresh.
        self._resamplers = {}
        self._resampler_for(1.0)
        if self._run is not None and not self._run.stretch:
            self._resampler_for(abs(self._run.speed))
        if dev_rate != self.rate:
            self._notify("notice.engine.resampling", device=name, rate=self.rate,
                         device_rate=dev_rate)
            log.info(t("notice.engine.resampling", device=name, rate=self.rate,
                       device_rate=dev_rate))
        self._fifo_gen = -1  # the new stream starts with an empty queue
        self._device_name = name
        self._latency_frames = round(float(stream.latency) * self.rate)
        self._stream_latency = float(stream.latency)
        self._cb_times.clear()
        self._dac_leads.clear()
        self._parked = False
        self._expect_finish = False
        self._died = False
        self._last_callback = self._clock()
        try:
            stream.start()
        except sd.PortAudioError as exc:
            self._stream = stream
            self._close_stream()
            raise EngineError("error.engine.open_failed", device=name,
                              error=str(exc)) from None
        self._stream = stream
        if self._saved_switch is None:
            self._saved_switch = sys.getswitchinterval()
        sys.setswitchinterval(SWITCH_S)

    def _close_stream(self) -> None:
        stream, self._stream = self._stream, None
        self._parked = False
        if stream is None:
            return
        if self._saved_switch is not None:
            sys.setswitchinterval(self._saved_switch)
            self._saved_switch = None
        self._expect_finish = True
        try:
            stream.close()
        except sd.PortAudioError as exc:
            log.warning(t("log.engine.close_failed", error=str(exc)))

    def _reopen(self, resume: bool, key: str) -> None:
        """Replace the stream: on the engine's device if it is still there,
        else on the default. ``resume`` keeps playing from the heard frame;
        otherwise playback pauses there."""
        with self._tlock:
            playing, run, until = self._playing, self._run, self._until
            heard = self._heard() if playing else self._anchor
        new = (None if not playing or run is None else
               _Run(self._plan(heard, until, run.speed, run.skip, run.loop), run.speed,
                    run.skip, run.loop, run.stretch))
        with self._tlock:
            if self._playing:
                self._start_run(heard, new)
            if not resume:
                self._playing = False
        self._close_stream()
        try:
            try:
                self._open(refresh=True)
            except EngineError:
                if self._device is None:
                    raise
                self._open(refresh=False, device=None)  # the default, then
        except EngineError as exc:
            with self._tlock:
                self._playing = False
            self._notify(exc.key, **exc.params)
            log.warning(str(exc))
            return
        self._notify(key, device=self._device_name, frames=self._blocksize)
        log.warning(t(key, device=self._device_name, frames=self._blocksize))

    # -- the helper thread -------------------------------------------------------

    def _start_thread(self) -> None:
        if not self._background or self._thread is not None:
            return
        if self._probe is not None:
            self._reporter = threading.Thread(target=self._report_loop,
                                              name="kuulas-debug", daemon=True)
            self._reporter.start()
        self._thread = threading.Thread(target=self._helper, name="kuulas-engine",
                                        daemon=True)
        self._thread.start()

    def _debug_numbers(self, since, blocksize: int | None = None):
        """``diag.Probe.summary`` plus the counters and the device."""
        def name_of(media_id: str) -> str:
            try:
                return self._project.media_item(media_id).name
            except KeyError:
                return media_id

        block_ms = (blocksize or self._blocksize) / self._dev_rate * 1000
        numbers, cursor = self._probe.summary(since, block_ms, name_of)
        numbers.update(late_blocks=self._late, failed_blocks=self._failed,
                       device=self._device_name, device_rate=self._dev_rate,
                       resampling=self._dev_rate != self.rate)
        return numbers, cursor

    def _report(self) -> None:
        """Print the line for what happened since the last one."""
        numbers, self._report_cursor = self._debug_numbers(self._report_cursor)
        diag.emit(diag.format_report(numbers))

    def _report_loop(self) -> None:
        while not self._halt.wait(1.0):
            with self._tlock:
                playing = self._playing
            if playing:
                try:
                    self._report()
                except Exception:  # the reporter must outlive any one bug
                    log.exception(t("log.engine.tick_failed"))

    def _helper(self) -> None:
        while not self._halt.wait(TICK_S):
            try:
                self._tick()
            except Exception:  # the helper must outlive any one bug
                log.exception(t("log.engine.tick_failed"))

    def _tick(self) -> None:
        """Every 250 ms: notices from the audio thread, the stream's health,
        late blocks, idle close, and decoding ahead."""
        with self._ctl:
            if self._closed:
                return
            self._drain_events()
            now = self._clock()
            with self._tlock:
                playing = self._playing
            stream = self._stream
            if stream is not None:
                if self._died or (not stream.active and not self._parked):
                    self._reopen(resume=False, key="notice.engine.device_changed")
                elif playing and now - self._last_callback > WATCHDOG_S:
                    self._reopen(resume=True, key="notice.engine.restarted")
                elif self._struggling(now):
                    self._escalate(now)
                elif not playing and now - self._last_active > IDLE_CLOSE_S:
                    self._close_stream()
                if playing:
                    self._last_active = now
        if playing:
            self._prefetch()

    def _struggling(self, now: float) -> bool:
        recent = [x for x in self._late_times if now - x < LATE_WINDOW_S]
        return (len(recent) >= LATE_COUNT
                and now - self._last_escalation >= LATE_WINDOW_S)

    def _escalate(self, now: float) -> None:
        """Late blocks: a bigger buffer first, then say so. Freezing the
        heaviest real-time layer comes with WP23a; there are none yet."""
        self._last_escalation = now
        self._late_times.clear()
        if self._blocksize < SAFE_BLOCKSIZE or self._latency_setting != SAFE_LATENCY:
            if self._probe is not None:
                numbers = self._debug_numbers((0, 0, 0, 0), self._blocksize)[0]
                diag.emit(diag.format_raise(
                    self._blocksize, SAFE_BLOCKSIZE, self._late,
                    numbers["cb_max_ms"], numbers["block_ms"]))
            self._blocksize = max(self._blocksize, SAFE_BLOCKSIZE)
            self._latency_setting = SAFE_LATENCY
            self._reopen(resume=True, key="notice.engine.struggling")
        else:
            self._notify("notice.engine.struggling", device=self._device_name,
                         frames=self._blocksize)
            log.warning(t("notice.engine.struggling", device=self._device_name,
                          frames=self._blocksize))

    def _drain_events(self) -> None:
        failures = 0
        while self._events:
            event = self._events.popleft()
            if event[0] == "failed":
                failures += 1
                log.error(t("log.engine.block_failed", error=event[1]))
            elif event[0] == "damaged":
                _, media_id, index, error = event
                try:
                    name = self._project.media_item(media_id).name
                except KeyError:
                    name = media_id
                when = _clock_text(index * self._store.step, self.rate)
                log.error(t("log.engine.media_damaged", media_id=media_id, name=name,
                            chunk=index, error=error))
                self._notify("notice.engine.media_damaged", ident=media_id,
                             name=name, time=when)
        if failures:
            self._notify("notice.engine.block_failed", count=self._failed)

    def _notify(self, key: str, ident: str | None = None, **params) -> None:
        """Show ``key`` to the user. The same notice again replaces the old
        one with a new id, so the UI shows it again without a pile-up."""
        tag = (key, ident)
        for old in [n for n in self._notices if n["tag"] == tag]:
            self._notices.remove(old)
        self._notice_id += 1
        self._notices.append({"id": self._notice_id, "key": key, "params": params,
                              "tag": tag})

    def _prefetch(self) -> None:
        """Read every clip's audio for the next few seconds into the
        read-ahead cache, so the audio thread finds it there."""
        with self._tlock:
            run, fed = self._run, self._fed
        if run is not None:
            self._read_ahead(run, fed, PREFETCH_S, evict=True)

    def _ahead(self, seconds: float, speed: float) -> int:
        return round(seconds * self.rate * max(1.0, abs(speed)))

    def _read_ahead(self, run: _Run, fed: int, seconds: float, *, evict: bool) -> None:
        """Fill the cache for ``seconds`` of ``run`` from its played frame
        ``fed`` (and, in a loop, from the loop's start). ``evict`` also drops
        chunks no longer wanted: only the helper does that."""
        plan, length = run.plan, self._project.length
        ahead = self._ahead(seconds, MAX_STRETCH if run.stretch else run.speed)
        if run.speed > 0:
            first = plan.position(fed, length)
            last = first + ahead
        else:
            last = plan.position(max(0, plan.length(length) - fed), length)
            first = max(0, last - ahead)
        windows = [(first, last)]
        if run.loop is not None:  # the wrap goes back to the loop's start
            windows.append((run.loop[0], run.loop[0] + ahead))
        self._fill_windows(windows, evict=evict)

    def _fill_windows(self, windows: list[tuple[int, int]], *,
                      evict: bool = False) -> None:
        """Read the chunks every clip needs for the programme-frame
        ``windows``. Never holds a lock the audio thread takes."""
        project, store = self._project, self._store
        step, now = store.step, time.monotonic()
        wanted: set[tuple[str, int]] = set()
        for first, last in windows:
            for track in project.tracks:
                for clip in track.clips:
                    lo, hi = max(first, clip.heard_start), min(last, clip.heard_end)
                    if hi <= lo:
                        continue
                    src = max(0, clip.offset + (lo - clip.start))
                    src_end = clip.offset + (hi - clip.start)
                    for index in range(src // step, (src_end - 1) // step + 1):
                        wanted.add((clip.media, index))
        for media_id, index in sorted(wanted):
            store.fill(media_id, index, now)
        if evict:
            store.evict(wanted, now)
