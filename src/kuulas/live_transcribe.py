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
        self.rate = rate
        self.folder = folder
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

    def _lane_step(self, track_id: str, lane: dict) -> dict:
        path = self.folder / lane["file"] if hasattr(self.folder, "__truediv__") else None
        flushed = self._flushed(path)
        done = lane["live"].done_frames if lane["live"] is not None else 0
        if chunk_window(flushed, done, self.rate, self._chunk_s) is None:
            return {"track": track_id, "waiting": True, "done_frames": done}
        if lane["live"] is None:
            if self._engine is None:
                self._engine = self._engine_factory()
            read = self._read
            if read is None:
                read = lambda start, end, p=path: _read_frames_soundfile(p, start, end)
            lane["live"] = LiveTranscriber(
                rate=self.rate, track_id=track_id, store=self.store,
                engine=self._engine, read_frames=read,
                chunk_s=self._chunk_s, ctx_s=self._ctx_s)
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

    def tick(self) -> list[dict]:
        """One chunk per lane that has a full one ready; per-lane statuses."""
        out = []
        for track_id, lane in self._lanes.items():
            if lane["failures"] >= MAX_LANE_FAILURES:
                continue
            out.append(self._lane_step(track_id, lane))
        return out
