"""Live take transcription (owner, 2026-11-01): searchable text while the take runs.

The take's progressive WAVs (kuulas_recorder.wavfile) are valid at every flush,
so a sidecar can read the newest full chunk of each lane, hand it to the speech
engine and collect word-timed text a few seconds behind the take (the owner
accepts a 5-10 s trail; measured latency is reported, never promised). The page
searches the collected words DURING the take for follow-up questions ("did I
say this already").

This module holds the pure parts, unit-tested without audio or an engine:
which frames to transcribe next (``chunk_window``), how a chunk's words merge
into the lane's text without duplicates (``merge_words``), and the searchable
in-memory store (``LiveTranscript``). The sidecar that drives them lives in
``record_session``; the engine runs warm in its own process (transcribe.py).
"""

from __future__ import annotations

import threading
import time


def chunk_window(flushed: int, done: int, rate: int, chunk_s: float = 5.0) -> tuple[int, int] | None:
    """The next [start, end) frames to transcribe, or None when nothing full is ready.

    Sequential per lane: chunk after chunk as the take's flushed length allows
    (``flushed`` frames are on disk; ``done`` frames already transcribed). A
    short bit past a chunk boundary is not transcribed early: it belongs to the
    next chunk, so no word is read twice at a cut point.
    """
    chunk = int(chunk_s * rate)
    if chunk <= 0:
        raise ValueError("chunk_s must be positive")
    if done < 0 or flushed < done:
        raise ValueError("bad offsets")
    if flushed - done < chunk:
        return None
    return (done, done + chunk)


def merge_words(old: list[dict], new: list[dict], since: int) -> list[dict]:
    """``old`` with the re-read overlap replaced: old words before ``since`` + ``new``.

    A chunk is read with a little context before its start so the engine hears
    whole words; the words that fall in that context were already transcribed
    with the previous chunk, so the new read replaces everything at/after
    ``since`` (flicks on the media clock, as transcribe.py stores them).
    """
    kept = [w for w in old if w["s"] < since]
    return kept + list(new)


class LiveTranscript:
    """The take-so-far's words per track, searchable while it records.

    Thread-safe: the sidecar adds from its thread while the server answers
    searches. Times are flicks on the take's clock (transcribe.py); the track
    id keys each lane, so attribution comes from the track (the engine has no
    diarization).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._by_track: dict[str, list[dict]] = {}

    def add(self, track_id: str, words: list[dict], since: int) -> None:
        """Merge one chunk's words into the track's text (see ``merge_words``)."""
        with self._lock:
            current = self._by_track.get(track_id, [])
            self._by_track[track_id] = merge_words(current, words, since)

    def words(self, track_id: str | None = None) -> list[dict]:
        """The collected words in time order: one track's, or every track's merged."""
        with self._lock:
            if track_id is not None:
                return [dict(w, track=track_id) for w in self._by_track.get(track_id, [])]
            out = [dict(w, track=t) for t, ws in self._by_track.items() for w in ws]
        out.sort(key=lambda w: w["s"])
        return out

    def search(self, query: str) -> list[dict]:
        """Word positions matching ``query``: case-insensitive, phrases across boundaries.

        Returns the matching words (each with its track), time-ordered; a phrase
        matches consecutive words in one track, so a two-person overlap never
        makes a false phrase.
        """
        terms = query.lower().split()
        with self._lock:
            tracks = {t: list(ws) for t, ws in self._by_track.items()}
        if not terms:
            out = [dict(w, track=t) for t, ws in tracks.items() for w in ws
                   if any(True for _ in [w])]
            out.sort(key=lambda w: w["s"])
            return out
        hits = []
        for track_id, words in tracks.items():
            texts = [w["w"].lower() for w in words]
            for i in range(len(words)):
                if all(i + j < len(words) and terms[j] in texts[i + j]
                       for j in range(len(terms))):
                    hits.extend(dict(words[i + j], track=track_id) for j in range(len(terms)))
        hits.sort(key=lambda w: w["s"])
        return hits


from .clock import FLICKS


class LiveTranscriber:
    """One lane's chunk loop: read the next full chunk, transcribe, merge, remember.

    The engine and the audio read are injected (tests use fakes; the sidecar in
    record_session passes the warm Orukeet process and soundfile reads of the
    progressive WAV). ``engine(audio, rate)`` returns word dicts with times in
    SECONDS from the start of the audio it was given (Orukeet's shape); they
    are stored on the take's clock in flicks, as transcribe.py stores them.
    """

    def __init__(self, *, rate: int, track_id: str, store: LiveTranscript,
                 engine, read_frames, chunk_s: float = 5.0, ctx_s: float = 0.5):
        self.rate = rate
        self.track_id = track_id
        self.store = store
        self.engine = engine
        self.read_frames = read_frames
        self.chunk_s = chunk_s
        self.ctx_s = ctx_s
        self.done_frames = 0

    def step(self, flushed: int) -> dict | None:
        """Transcribe the next ready chunk (``flushed`` frames are on disk), else None."""
        window = chunk_window(flushed, self.done_frames, self.rate, self.chunk_s)
        if window is None:
            return None
        start, end = window
        start_flicks = round(start / self.rate * FLICKS)
        ctx = int(self.ctx_s * self.rate)
        read_start = max(0, start - ctx)
        audio = self.read_frames(read_start, end)
        kept = []
        for item in self.engine(audio, self.rate):
            text = str(item.get("word", item.get("text", item.get("w", "")))).strip()
            if not text:
                continue
            s_sec = float(item.get("start", item.get("s", 0.0))) + read_start / self.rate
            e_sec = float(item.get("end", item.get("e", 0.0))) + read_start / self.rate
            s = round(s_sec * FLICKS)
            e = max(round(e_sec * FLICKS), s + 1)
            # A word starting in the context was transcribed with the previous chunk.
            if s < start_flicks:
                continue
            kept.append({"w": text, "s": s, "e": e, "spk": ""})
        self.store.add(self.track_id, kept, since=start_flicks)
        self.done_frames = end
        return {"start": start, "end": end, "words": len(kept)}

    #: A tail shorter than this is not transcribed (too little to say).
    MIN_TAIL_S = 0.25

    def finish(self, flushed: int) -> dict | None:
        """The trailing partial chunk when the take is over, else None.

        The live loop transcribes only full chunks; the tail between the last
        one and the take's end is read here, once, so stop loses no words.
        """
        if flushed - self.done_frames < int(self.MIN_TAIL_S * self.rate):
            return None
        start, end = self.done_frames, flushed
        start_flicks = round(start / self.rate * FLICKS)
        ctx = int(self.ctx_s * self.rate)
        read_start = max(0, start - ctx)
        audio = self.read_frames(read_start, end)
        kept = []
        for item in self.engine(audio, self.rate):
            text = str(item.get("word", item.get("text", item.get("w", "")))).strip()
            if not text:
                continue
            s_sec = float(item.get("start", item.get("s", 0.0))) + read_start / self.rate
            e_sec = float(item.get("end", item.get("e", 0.0))) + read_start / self.rate
            w_s = round(s_sec * FLICKS)
            w_e = max(round(e_sec * FLICKS), w_s + 1)
            if w_s < start_flicks:
                continue
            kept.append({"w": text, "s": w_s, "e": w_e, "spk": ""})
        self.store.add(self.track_id, kept, since=start_flicks)
        self.done_frames = end
        return {"start": start, "end": end, "words": len(kept), "tail": True}


#: Give up on a lane after this many engine errors in a row (the take goes on
#: regardless; a lane out of live text is a gap, never a stopped take).
MAX_LANE_FAILURES = 3


def flushed_frames(path) -> int:
    """Frames the progressive WAV's header names: everything synced so far.

    The recorder rewrites the data-size field at every flush after the audio it
    covers (kuulas_recorder.wavfile), so the header is the take's safe length.
    A missing or half-written file reads as 0: nothing to transcribe yet.
    """
    import struct
    try:
        with open(path, "rb") as f:
            head = f.read(44)
    except OSError:
        return 0
    if len(head) < 44 or head[:4] != b"RIFF":
        return 0
    return struct.unpack("<I", head[40:44])[0] // 3  # mono 24-bit: 3 bytes a frame


def _read_frames_soundfile(path, start, end):
    """Samples [start, end) of a take WAV as floats (the sidecar's default reader)."""
    import soundfile as sf
    data, _ = sf.read(str(path), start=start, stop=end, dtype="float32",
                      always_2d=False)
    return data


class LiveTranscribeSidecar:
    """One take's live transcription across its lanes, driven by ``tick``.

    The record status watcher ticks the sidecar; each tick asks every lane for
    its flushed length and transcribes at most one chunk per lane, so a slow
    engine never blocks the watcher (the engine call itself is the only slow
    part, and it is the point of the tick). The engine is built lazily on the
    first chunk (engine_factory) so opening the record view never loads a
    model. Returns per-lane statuses for the record channel to publish.
    """

    def __init__(self, *, rate: int, folder, lane_files: dict[str, str],
                 engine_factory, store: LiveTranscript | None = None,
                 chunk_s: float = 5.0, ctx_s: float = 0.5,
                 read_frames=None, flushed=flushed_frames):
        from pathlib import Path
        self.rate = rate
        self.folder = Path(folder)
        self.store = store or LiveTranscript()
        self._engine_factory = engine_factory
        self._engine = None
        self._read = read_frames
        self._flushed = flushed
        self._lanes = {
            track_id: {"file": name, "live": None, "failures": 0, "error": None}
            for track_id, name in lane_files.items()
        }
        self._chunk_s = chunk_s
        self._ctx_s = ctx_s

    def _ensure_lane(self, track_id: str, lane: dict):
        """Spin up the lane's transcriber (and the shared engine) on demand."""
        if lane["live"] is not None:
            return
        if self._engine is None:
            self._engine = self._engine_factory()
        path = self.folder / lane["file"]
        read = self._read
        if read is None:
            read = lambda start, end, p=path: _read_frames_soundfile(p, start, end)
        lane["live"] = LiveTranscriber(
            rate=self.rate, track_id=track_id, store=self.store,
            engine=self._engine, read_frames=read,
            chunk_s=self._chunk_s, ctx_s=self._ctx_s)

    def _lane_step(self, track_id: str, lane: dict) -> dict:
        path = self.folder / lane["file"]
        flushed = self._flushed(path)
        done = lane["live"].done_frames if lane["live"] is not None else 0
        if chunk_window(flushed, done, self.rate, self._chunk_s) is None:
            return {"track": track_id, "waiting": True, "done_frames": done}
        self._ensure_lane(track_id, lane)
        try:
            status = lane["live"].step(flushed)
        except Exception as error:  # the take never stops for transcription
            lane["failures"] += 1
            lane["error"] = str(error)
            return {"track": track_id, "error": str(error),
                    "failures": lane["failures"],
                    "disabled": lane["failures"] >= MAX_LANE_FAILURES}
        lane["failures"] = 0
        if status is None:
            return {"track": track_id, "waiting": True,
                    "done_frames": lane["live"].done_frames}
        return {"track": track_id, **status, "done_frames": lane["live"].done_frames}

    def finish(self, cancel: "threading.Event | None" = None) -> list[dict]:
        """The take is over: drain each lane's backlog, then its trailing chunk.

        A slow engine can fall behind during the take; the backlog is on disk,
        not in memory (one chunk in flight at a time), so draining it here
        loses no words. ``cancel`` stops the drain BETWEEN chunks and reports
        the lane's coverage (done vs flushed frames); a hung single engine
        call runs out - nothing interrupts it, but the take never waits on it.
        """
        out = []
        for track_id, lane in self._lanes.items():
            path = self.folder / lane["file"]
            try:
                self._ensure_lane(track_id, lane)
                live = lane["live"]
                while chunk_window(self._flushed(path), live.done_frames,
                                   self.rate, self._chunk_s) is not None:
                    if cancel is not None and cancel.is_set():
                        out.append({"track": track_id, "cancelled": True,
                                    "done_frames": live.done_frames,
                                    "flushed_frames": self._flushed(path)})
                        break
                    status = live.step(self._flushed(path))
                    if status is not None:
                        out.append({"track": track_id, **status})
                else:
                    status = live.finish(self._flushed(path))
                    if status is not None:
                        out.append({"track": track_id, **status})
            except Exception as error:
                lane["error"] = str(error)
                out.append({"track": track_id, "error": str(error)})
        return out

    def tick(self) -> list[dict]:
        """One chunk per lane that has a full one ready; per-lane statuses."""
        out = []
        for track_id, lane in self._lanes.items():
            if lane["failures"] >= MAX_LANE_FAILURES:
                continue
            out.append(self._lane_step(track_id, lane))
        return out


class LiveTranscribeRunner:
    """The sidecar's thread: throttled ticks, never a risk to the take.

    The record watcher only pokes (``poke``); transcription runs here so a slow
    engine never blocks the take's level frames or its stop. Ticks are at most
    ``min_interval_s`` apart; a poke while a tick runs folds into the next one.
    An engine that keeps failing only loses its lane (the sidecar's rule), and
    an unexpected error is logged, counted and survived: the thread dies only
    on ``stop``.
    """

    def __init__(self, sidecar: LiveTranscribeSidecar, publish=None,
                 min_interval_s: float = 1.0, log=None):
        self.sidecar = sidecar
        self.publish = publish or (lambda statuses: None)
        self.min_interval_s = min_interval_s
        self._log = log
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self.errors = 0
        self.ticks = 0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="kuulas-live-transcribe")
        self._thread.start()

    def poke(self) -> None:
        """New audio may be ready: tick soon (the watcher thread calls this)."""
        self._wake.set()

    def stop(self, timeout: float = 30.0, flush: bool = True,
             block: bool = True) -> None:
        """Stop the thread; ``flush`` first transcribes what is left (the backlog
        and the trailing partial chunk) on the runner thread, so stop loses no
        words. With ``block=False`` the caller returns at once - the take's
        stop and import never wait on ASR - and the flush finishes in the
        background; ``wait`` observes completion, ``cancel`` cuts it short."""
        self._flush = flush
        self._stop.set()
        self._wake.set()
        if block and self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def wait(self, timeout: float) -> bool:
        """True once the runner thread has finished (the flush included)."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        if thread.is_alive():
            return False
        self._thread = None
        return True

    def cancel(self) -> None:
        """Cut a running flush short between chunks (a hung engine call runs out)."""
        self._cancel.set()

    @property
    def flushing(self) -> bool:
        """A flush was asked for and the runner thread is still doing it."""
        thread = self._thread
        return (self._stop.is_set() and self._flush and thread is not None
                and thread.is_alive())

    _flush = True

    def _run(self) -> None:
        last = 0.0
        while not self._stop.is_set():
            self._wake.wait(self.min_interval_s)
            self._wake.clear()
            if self._stop.is_set():
                break
            now = time.monotonic()
            wait = self.min_interval_s - (now - last)
            if wait > 0:
                if self._stop.wait(wait):
                    break
                self._wake.clear()
            try:
                statuses = self.sidecar.tick()
                self.ticks += 1
            except Exception as error:  # transcription never stops the take
                self.errors += 1
                if self._log:
                    self._log.warning("live transcription tick failed: %s", error)
                continue
            last = time.monotonic()
            interesting = [s for s in statuses if not s.get("waiting")]
            if interesting:
                self.publish(interesting)
        if self._flush:
            self._run_finish()

    def _run_finish(self) -> None:
        try:
            statuses = self.sidecar.finish(cancel=self._cancel)
        except Exception as error:
            self.errors += 1
            if self._log:
                self._log.warning("live transcription finish failed: %s", error)
            return
        if statuses:
            self.publish(statuses)
