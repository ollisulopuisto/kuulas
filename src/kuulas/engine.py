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
meters use it, so they do not run 20-45 ms ahead of the sound.

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
frames, so it jumps over a skip and runs at the speed. Fast playback with the
pitch kept (time-stretching) is not built and is refused.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import numpy as np
import sounddevice as sd
import soxr

from .media import CHUNK_SEC
from .messages import KuulasError, t
from .model import Project
from .playplan import PlaybackRequestError, PlayPlan, normalise_skip

log = logging.getLogger("kuulas.engine")

#: Frames per block: about 21 ms at 48 kHz, the plan's default.
BLOCKSIZE = 1024
#: The buffer late blocks raise it to (about 43 ms). WP23a will also use it
#: when the CPU meter shows sustained load over 60 %.
SAFE_BLOCKSIZE = 2048
#: The helper thread's period: prefetch, watchdog, device checks, notices.
TICK_S = 0.25
#: How far ahead the helper thread decodes media.
PREFETCH_S = 5.0
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
#: A frame past any project, for keeping a skip list unclipped.
_FAR = 2**62
#: "No resampler made for this speed" (None means none is needed).
_MISSING = object()


class EngineError(KuulasError):
    """Playback could not start: no device, or the device refused to open."""


class _Run:
    """One play's fixed parameters. Replaced as a whole under ``_tlock``, so
    the audio thread reads one consistent reference per block."""

    __slots__ = ("plan", "skip", "speed")

    def __init__(self, plan: PlayPlan, speed: float, skip: tuple[tuple[int, int], ...]):
        self.plan, self.speed, self.skip = plan, speed, skip


def _check_speed(rate: object, preserve_pitch: bool) -> float:
    try:
        speed = float(rate)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise PlaybackRequestError("error.engine.bad_speed", speed=str(rate)) from None
    if not math.isfinite(speed) or not MIN_SPEED <= abs(speed) <= MAX_SPEED:
        raise PlaybackRequestError("error.engine.bad_speed", speed=str(rate))
    if preserve_pitch and abs(speed) != 1.0:
        # Time-stretching (pedalboard's Rubber Band, rendered ahead in
        # chunks) is not built yet. Refusing is better than a UI that asks
        # for fast listening and silently gets chipmunk speech.
        raise PlaybackRequestError("error.engine.stretch_unavailable", speed=str(rate))
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
        #: media id -> indices of chunks that failed to decode
        self.damaged: dict[str, set[int]] = {}

    def read(self, media_id: str, first: int, count: int) -> np.ndarray:
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
                 background: bool = True):
        self._session = session
        self._project: Project = session.state
        self.rate = self._project.rate
        self._blocksize = int(blocksize)
        self._device = device
        self._clock = clock
        self._background = background

        #: Events from the audio thread, read by the helper thread. A deque's
        #: append and popleft are atomic, so neither side waits.
        self._events: deque = deque(maxlen=1000)
        self._store = _SafeStore(session.store, self.rate, self._events)

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

        # Counters and timestamps the audio thread writes.
        self._failed = 0
        self._late = 0
        self._late_times: deque = deque(maxlen=64)
        self._last_callback = clock()

        # Control side (API threads and the helper thread), under _ctl.
        self._ctl = threading.RLock()
        self._stream = None
        self._device_name = ""
        self._dev_rate = self.rate
        self._latency_frames = 0
        self._expect_finish = False
        self._died = False
        self._last_active = clock()
        self._last_escalation = -math.inf
        self._notices: deque = deque(maxlen=MAX_NOTICES)
        self._notice_id = 0
        self._closed = False
        self._halt = threading.Event()
        self._thread: threading.Thread | None = None

        session.subscribe(self.set_project)

    # -- public surface ------------------------------------------------------

    def set_project(self, project: Project) -> None:
        """The project to play from the next block on. Called by the session
        after every change; one attribute assignment, so the audio thread
        never sees half a project."""
        self._project = project

    def play(self, at: int | None = None, until: int | None = None, *,
             rate: float = 1.0, preserve_pitch: bool = True,
             skip=None) -> None:
        """Play from ``at`` (default: where the playhead is) to ``until``
        (default: the end of the project; below ``at`` when ``rate`` is
        negative, default the start).

        ``skip``: frame ranges ``(a, b)`` to jump over, crossfaded; empty or
        None plays everything. ``rate``: tape speed, ``MIN_SPEED`` to
        ``MAX_SPEED`` either way (negative is backward); with
        ``preserve_pitch`` (the default) only 1 and -1 are available, since
        time-stretching is not built. A bad ``rate`` or ``skip`` raises
        ``PlaybackRequestError``, no device ``EngineError``; nothing changes
        then."""
        speed = _check_speed(rate, preserve_pitch)
        skip_list = normalise_skip(skip, 0, _FAR)
        with self._ctl:
            if self._stream is not None and (self._died or not self._stream.active):
                self._close_stream()  # died since the last tick: open afresh
            if self._stream is None:
                self._open(refresh=True)
            self._resampler_for(abs(speed))
            with self._tlock:
                gen, run = self._gen, self._run
                continuing = at is None and self._playing
                if continuing:
                    start = self._heard()
                else:
                    start = self._anchor if at is None else max(0, int(at))
                # Same speed (forward) and skip list, only a new end: the
                # run goes on with nothing re-queued, as before skips.
                keep = (continuing and run is not None and speed > 0
                        and run.speed == speed and run.skip == skip_list)
                lo = self._anchor if keep else start
            new = _Run(self._plan(lo, until, speed, skip_list), speed, skip_list)
            with self._tlock:
                if keep and self._gen == gen and self._playing:
                    self._run = new
                else:
                    self._start_run(start, new)
                self._until = until
                self._playing = True
            self._last_active = self._clock()
            self._last_callback = self._clock()
            self._start_thread()

    def stop(self) -> None:
        """Stop where the sound was: the playhead stays at the heard frame."""
        with self._ctl, self._tlock:
            if self._playing:
                self._start_run(self._heard())
                self._playing = False
            self._last_active = self._clock()

    def seek(self, frame: int) -> None:
        """Move the playhead; playback, if on, continues from there at the
        same speed, still skipping the same ranges."""
        frame = max(0, int(frame))
        with self._tlock:
            run, until = self._run, self._until
        new = None if run is None else _Run(self._plan(frame, until, run.speed, run.skip),
                                            run.speed, run.skip)
        with self._tlock:
            self._start_run(frame, new)

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
        with self._tlock:
            playing, until, run = self._playing, self._until, self._run
            position = self._heard() if playing else self._anchor
        live = run if playing and run is not None else None
        with self._ctl:
            notices = [{"id": n["id"], "key": n["key"], "params": n["params"],
                        "text": t(n["key"], **n["params"])} for n in self._notices]
            return {
                "playing": playing,
                "position": int(position),
                "until": until,
                "speed": live.speed if live else 1.0,
                "skip": [list(r) for r in live.skip] if live else [],
                "rate": self.rate,
                "device": self._device_name,
                "device_rate": self._dev_rate,
                "resampling": self._dev_rate != self.rate,
                "blocksize": self._blocksize,
                "failed_blocks": self._failed,
                "late_blocks": self._late,
                "damaged": sorted(self._store.damaged),
                "notices": notices,
            }

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
        self._gen += 1

    def _played(self) -> int:
        """Frames of the run's played timeline that have reached the ear:
        device frames since the anchor, at |speed| x the project rate, minus
        the device's output latency (which holds that much more)."""
        speed = abs(self._run.speed) if self._run is not None else 1.0
        played = self._out * speed * self.rate / self._dev_rate
        return max(0, round(played - self._latency_frames * speed))

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

    def _plan(self, start: int, until: int | None, speed: float,
              skip: tuple[tuple[int, int], ...]) -> PlayPlan:
        """The plan for playing from ``start`` (control side, outside
        ``_tlock``: it computes the crossfade curves)."""
        length = self._project.length
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

    def _callback(self, outdata, frames, _time, status) -> None:
        """PortAudio's callback. Never raises: a failing block is silence."""
        now = self._clock()
        self._last_callback = now
        try:
            if status.output_underflow:
                self._late += 1
                self._late_times.append(now)
            began = time.perf_counter()
            outdata[:] = self._render(frames)
            if time.perf_counter() - began > frames / self._dev_rate:
                self._late += 1
                self._late_times.append(now)
        except Exception as exc:  # noqa: BLE001 - the audio callback never raises
            outdata.fill(0)
            self._failed += 1
            self._events.append(("failed", repr(exc)))

    def _render(self, frames: int) -> np.ndarray:
        """``(frames, 2)`` float32 at the device rate: the next block to play."""
        out = np.zeros((frames, 2), dtype=np.float32)
        with self._tlock:
            playing, gen, fed, run = self._playing, self._gen, self._fed, self._run
        if not playing or run is None:
            return out
        project = self._project
        speed = abs(run.speed)
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
        while have < frames and not self._flushed:
            n = min(max(1, math.ceil((frames - have) * ratio)), max(0, end - fed))
            if n > 0:
                if run.speed > 0:
                    block = plan.read(project, self._store, fed, n)
                else:  # backward: the played timeline from its end
                    block = plan.read(project, self._store, end - fed - n, n)[:, ::-1]
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
                if done:
                    self._playing = False
                    self._anchor = (plan.final(project.length) if run.speed > 0
                                    else plan.lo)
                    self._fed = self._out = 0
        return out

    def _finished(self) -> None:
        """PortAudio's finished callback: the stream stopped. Unless we
        stopped it, the device went away."""
        if not self._expect_finish:
            self._died = True

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
                  "latency": "high", "device": device, "callback": self._callback,
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
        if self._run is not None:
            self._resampler_for(abs(self._run.speed))
        if dev_rate != self.rate:
            self._notify("notice.engine.resampling", device=name, rate=self.rate,
                         device_rate=dev_rate)
            log.info(t("notice.engine.resampling", device=name, rate=self.rate,
                       device_rate=dev_rate))
        self._fifo_gen = -1  # the new stream starts with an empty queue
        self._device_name = name
        self._latency_frames = round(float(stream.latency) * self.rate)
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

    def _close_stream(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
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
               _Run(self._plan(heard, until, run.speed, run.skip), run.speed, run.skip))
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
        self._thread = threading.Thread(target=self._helper, name="kuulas-engine",
                                        daemon=True)
        self._thread.start()

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
                if self._died or not stream.active:
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
        if self._blocksize < SAFE_BLOCKSIZE:
            self._blocksize = SAFE_BLOCKSIZE
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
        """Decode every clip's audio for the next few seconds now, so the
        audio thread finds it cached. One frame per decode chunk is enough
        to make the store decode and cache that chunk."""
        project = self._project
        with self._tlock:
            run, fed = self._run, self._fed
        if run is None:
            return
        plan, length = run.plan, project.length
        ahead = round(PREFETCH_S * self.rate * max(1.0, abs(run.speed)))
        if run.speed > 0:
            first = plan.position(fed, length)
            last = first + ahead
        else:
            last = plan.position(max(0, plan.length(length) - fed), length)
            first = max(0, last - ahead)
        step = self._store.step
        for track in project.tracks:
            for clip in track.clips:
                lo, hi = max(first, clip.heard_start), min(last, clip.heard_end)
                if hi <= lo:
                    continue
                src = clip.offset + (lo - clip.start)
                src_end = src + (hi - lo)
                at = src
                while at < src_end:
                    self._store.read(clip.media, at, 1)
                    at = (at // step + 1) * step
