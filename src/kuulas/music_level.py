"""Set music level (Auto-mix in Kuulas, phase 1): the music beds' level by
measurement instead of by ear.

The rule is the automixer's (``automixer.stems_mix``, ``BED_UNDER_SPEECH_DB``):

* ``speech_lufs``: integrated loudness (BS.1770, K-weighted, gated) of the
  speech tracks summed, counted only where anyone is speaking
  (``stems.anyone_speaking``: the OR of the speech lanes Auto-Silence and the
  ducking already compute);
* ``bed_lufs``: the loudest 3 s short-term moment of the music tracks summed;
* ``change = speech_lufs + offset_db - bed_lufs``.

The automixer's own offset is -1 dB (its beds are levelled against processed,
compressed speech). Here the default is -10 dB: the edit is unprocessed and the
owner asked for the beds clearly under the voice (2026-10-20).

**Repeatable.** The music is measured WITHOUT its tracks' own gain (and
without their automation, the ducking, which the automixer also measures
before): the command computes the track gain the beds need, so running it
twice gives the same gains. Everything else is as heard: clip gain, envelopes,
fades, muted clips and gates are silence. With ``mode == "common"`` (default)
one change is added to every music track's gain relative to the loudest one,
so their balance is kept; ``"per_track"`` levels each track on its own.

**Speech as heard.** The speech tracks are measured with their gain and
automation, each placed in the stereo bus at the centre with the power pan law
(-3 dB a side), so a mono voice reads what it contributes to the mix (the
automixer's ``SPEECH_PAN_LAW``). Narration tracks count as speech. Muted tracks
count for nothing, music or speech.

Memory: one pass over the timeline in ``CHUNK_SEC`` steps, reads streamed
(docs/MEMORY.md); the meters keep 100 ms block powers, not audio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import numpy as np
from speechmix.meter import IntegratedMeter

from . import caches, mixer, priority
from .analysis import hop_frames, speech_lanes
from .curves import gain as db_gain
from .media import streaming
from .ops import CLIP_GAIN_RANGE, EditError

if TYPE_CHECKING:
    from .model import Project, Track

#: Bump when the numbers this module computes change (the ``key``).
ALGORITHM = "music-level@1"

#: How far under the speech the beds' loudest moment sits, dB (owner, 2026-10-20).
DEFAULT_OFFSET_DB = -10.0
OFFSET_RANGE = (-30.0, 0.0)
#: The automixer's fixed rule, for reference (``stems_mix.BED_UNDER_SPEECH_DB``).
AUTOMIXER_OFFSET_DB = 1.0

MODES = ("common", "per_track")
SPEECH_KINDS = ("speech", "narration")

#: Seconds of the timeline read per step: the speech bus, the music bus (or
#: one per music track) and one stem at a time, float64 stereo.
CHUNK_SEC = 15

#: A track gain the command never goes past: the inspector's gain range.
GAIN_RANGE = CLIP_GAIN_RANGE


def speech_tracks(p: Project) -> list[Track]:
    return [t for t in p.tracks if t.kind in SPEECH_KINDS and t.clips and not t.mute]


def music_tracks(p: Project) -> list[Track]:
    return [t for t in p.tracks if t.kind == "music" and t.clips and not t.mute]


def parse_offset(value) -> float:
    """The offset from a request: a number in ``OFFSET_RANGE``, else an error."""
    if value is None:
        return DEFAULT_OFFSET_DB
    try:
        v = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        v = float("nan")
    low, high = OFFSET_RANGE
    if not (low <= v <= high):  # also false for nan
        raise EditError("error.music_level.bad_offset", low=low, high=high)
    return v


def parse_mode(value) -> str:
    if value is None:
        return "common"
    if value not in MODES:
        raise EditError("error.edit.bad_arguments", name="set_music_level",
                        detail=f"mode {value!r}")
    return str(value)


def relative_gains(p: Project) -> dict[str, float]:
    """Each music track's gain against the loudest-set one (0 for it): the
    balance ``"common"`` keeps. Independent of where they all sit, so the
    measurement repeats after the gains moved together."""
    tracks = music_tracks(p)
    if not tracks:
        return {}
    top = max(t.gain_db for t in tracks)
    return {t.id: round(t.gain_db - top, 6) for t in tracks}


def key(p: Project, mode: str = "common") -> str:
    """What a measurement depends on, as a content key (``caches.key``): the
    media of the measured tracks, the speech tracks as they sound and the
    music tracks without their gain (but with their balance in ``"common"``).
    A music gain moved by this command changes no key. Raises
    ``caches.CacheKeyError`` when the key cannot be made (fail closed)."""
    skip = ("name", "target_lufs", "solo", "pan", "bus")
    speech = speech_tracks(p)
    music = music_tracks(p)
    shas = sorted({p.media_item(c.media).sha256
                   for t in (*speech, *music) for c in t.clips})
    params = {
        "rate": p.rate, "mode": mode,
        "speech": [{k: v for k, v in t.to_dict().items() if k not in skip}
                   for t in speech],
        "music": [{k: v for k, v in t.to_dict().items()
                   if k not in (*skip, "gain_db", "automation")} for t in music],
        "balance": relative_gains(p) if mode == "common" else {},
    }
    return caches.key(shas, params, ALGORITHM)


def _speaking(p: Project, store) -> np.ndarray | None:
    """Per analysis hop: is anyone speaking (``stems.anyone_speaking``)? The
    speech lanes of the speech and narration tracks; None when there are none."""
    as_speech = replace(p, tracks=tuple(
        replace(t, kind="speech") if t.kind == "narration" else t for t in p.tracks))
    lanes = speech_lanes(as_speech, store)
    if not lanes.speakers:
        return None
    anyone = np.zeros(max(len(lane.on) for lane in lanes.speakers), dtype=bool)
    for lane in lanes.speakers:
        on = np.asarray(lane.on, dtype=bool)
        anyone[: on.size] |= on
    return anyone


def _channels(p: Project, track: Track) -> int:
    if track.mono:
        return 1
    return max(1, min(2, max(p.media_item(c.media).channels for c in track.clips)))


#: Power pan law at the centre: a mono stem goes to both sides at -3 dB, so the
#: stereo bus reads the mono loudness (speechmix ``pan_gains(0, "power")``).
_CENTRE = math.sqrt(0.5)


def _into(bus: np.ndarray, stem: np.ndarray, gain: float = 1.0) -> None:
    if stem.shape[0] == 1:
        bus += stem[0] * (_CENTRE * gain)
    else:
        bus += stem[:2] * gain


def _finite(value) -> float | None:
    if value is None:
        return None
    v = float(value)
    return round(v, 2) if math.isfinite(v) else None

def measure(p: Project, store, mode: str = "common") -> dict:
    """``{speech_lufs, bed_lufs, beds: {track_id: lufs}, balance, key, mode,
    music_tracks, reason}`` for the snapshot ``p``. ``reason`` is
    ``"no_speech"`` or ``"no_music"`` (and the levels None) when there is
    nothing to level by or nothing to level. Pure on the snapshot: the caller
    holds no lock."""
    mode = parse_mode(mode)
    out = {"speech_lufs": None, "bed_lufs": None, "beds": {}, "mode": mode,
           "balance": relative_gains(p), "reason": None,
           "music_tracks": [t.id for t in music_tracks(p)]}
    try:
        out["key"] = key(p, mode)
    except caches.CacheKeyError:
        out["key"] = None
    speech, music = speech_tracks(p), music_tracks(p)
    if not music:
        return {**out, "reason": "no_music"}
    speaking = _speaking(p, store) if speech else None
    if speaking is None or not speaking.any():
        return {**out, "reason": "no_speech"}
    speech_lufs, peaks = _scan(p, store, speaking, out["balance"], mode)
    if speech_lufs is None:
        return {**out, "reason": "no_speech"}
    return _answer({**out, "speech_lufs": speech_lufs}, peaks, mode)


def _scan(p: Project, store, speaking: np.ndarray, balance: dict[str, float],
          mode: str) -> tuple[float | None, dict[str, float | None]]:
    """One pass over the timeline: ``(speech LUFS while anyone speaks, the
    loudest short-term LUFS of the beds)``; the beds keyed ``""`` (their sum,
    ``"common"``) or by track id."""
    speech, music = speech_tracks(p), music_tracks(p)
    hop = hop_frames(p.rate)
    talk = IntegratedMeter(p.rate)
    common = mode == "common"
    beds = {"": IntegratedMeter(p.rate)} if common else {
        t.id: IntegratedMeter(p.rate) for t in music}
    step = CHUNK_SEC * p.rate
    for first in range(0, p.length, step):
        priority.checkpoint()
        count = min(step, p.length - first)
        # A scan from start to end: its audio is not kept (docs/MEMORY.md).
        with streaming():
            bus = np.zeros((2, count))
            for t in speech:
                _into(bus, mixer.track_stem(t, store, first, count, _channels(p, t),
                                            as_heard=True, rate=p.rate))
            hops = np.arange(first, first + count) // hop
            flags = np.zeros(count, dtype=bool)
            inside = hops < speaking.size
            flags[inside] = speaking[hops[inside]]
            talk.add(bus, flags)
            bus[:] = 0.0
            for t in music:
                # Without the track's own gain and automation: repeatable.
                stem = mixer.track_stem(t, store, first, count, _channels(p, t),
                                        as_heard=False, rate=p.rate)
                _into(bus, stem, db_gain(balance[t.id]) if common else 1.0)
                if not common:
                    beds[t.id].add(bus)
                    bus[:] = 0.0
            if common:
                beds[""].add(bus)
            del bus
    spoken = talk.speech()
    speech_lufs = _finite(talk.value(keep=spoken > 0.5) if spoken.size else None)
    return speech_lufs, {ident: _finite(m.short_term_max()) for ident, m in beds.items()}


def _answer(out: dict, peaks: dict[str, float | None], mode: str) -> dict:
    if mode == "common":
        bed = peaks[""]
        if bed is None:
            return {**out, "reason": "no_music"}
        return {**out, "bed_lufs": bed}
    found = {k: v for k, v in peaks.items() if v is not None}
    if not found:
        return {**out, "reason": "no_music"}
    return {**out, "bed_lufs": max(found.values()), "beds": found}


@dataclass(frozen=True)
class Plan:
    """What applying gives: ``gains`` per music track, and how far each was
    clamped (``clamped``: track ids that hit ``GAIN_RANGE``)."""

    change_db: float
    gains: dict[str, float]
    clamped: tuple[str, ...]


def _clamp(value: float) -> float:
    low, high = GAIN_RANGE
    return round(max(low, min(high, value)), 2)


def solve(measured: dict, offset_db: float) -> Plan:
    """The music track gains that put the beds' loudest moment ``offset_db``
    under the speech. ``measured`` is ``measure``'s answer with no ``reason``."""
    speech, mode = measured["speech_lufs"], measured.get("mode", "common")
    change = round(speech + offset_db - measured["bed_lufs"], 2)
    if mode == "common":
        raw = {tid: rel + change for tid, rel in measured["balance"].items()}
    else:
        raw = {tid: speech + offset_db - lufs
               for tid, lufs in measured["beds"].items()}
    gains = {tid: _clamp(v) for tid, v in raw.items()}
    clamped = tuple(tid for tid, v in raw.items()
                    if abs(gains[tid] - round(v, 2)) > 1e-9)
    return Plan(change, gains, clamped)


def distance(p: Project, measured: dict) -> float | None:
    """Where the beds' loudest moment sits against the speech with the music
    gains ``p`` has, dB (negative: under). None without a usable measurement."""
    speech, bed = measured.get("speech_lufs"), measured.get("bed_lufs")
    if speech is None or bed is None:
        return None
    gains = {t.id: t.gain_db for t in p.tracks}
    if measured.get("mode", "common") == "common":
        here = [gains[tid] - rel for tid, rel in measured["balance"].items()
                if tid in gains]
        if not here:
            return None
        return round(bed + max(here) - speech, 2)
    heard = [lufs + gains[tid] for tid, lufs in measured["beds"].items() if tid in gains]
    return round(max(heard) - speech, 2) if heard else None


def check(measured: dict) -> None:
    """Refuse a measurement that has nothing to apply, with the reason."""
    reason = measured.get("reason")
    if reason == "no_music":
        raise EditError("error.music_level.no_music")
    if reason == "no_speech":
        raise EditError("error.music_level.no_speech")
    numbers = (measured.get("speech_lufs"), measured.get("bed_lufs"))
    shapes = (measured.get("balance"), measured.get("beds"))
    if (not all(isinstance(v, int | float) for v in numbers)
            or not all(isinstance(v, dict) for v in shapes)):
        raise EditError("error.edit.bad_arguments", name="set_music_level",
                        detail="measured")


def record(measured: dict, offset_db: float, plan: Plan, at: str | None = None) -> dict:
    """The ``Project.mix_done["bed_level"]`` entry (phase 3: an export can tell
    the automixer the beds are levelled already). ``gains`` and ``key`` make it
    checkable: ``bed_level_current``."""
    return {"offset_db": offset_db, "speech_lufs": measured["speech_lufs"],
            "bed_lufs": measured["bed_lufs"], "mode": measured.get("mode", "common"),
            "change_db": plan.change_db, "gains": dict(plan.gains),
            "key": measured.get("key"), "algorithm": ALGORITHM,
            **({"set_at": at} if at else {})}


def bed_level_current(p: Project) -> dict | None:
    """The recorded bed level, only while it still holds: the music tracks have
    the gains it set and nothing it measured has changed (the same ``key``).
    None otherwise, or when the key cannot be made (fail closed)."""
    entry = (p.mix_done or {}).get("bed_level")
    if not entry or not entry.get("key"):
        return None
    try:
        if key(p, entry.get("mode", "common")) != entry["key"]:
            return None
    except caches.CacheKeyError:
        return None
    gains = {t.id: t.gain_db for t in music_tracks(p)}
    if set(gains) != set(entry.get("gains", {})):
        return None
    if any(abs(gains[tid] - g) > 0.005 for tid, g in entry["gains"].items()):
        return None
    return entry
