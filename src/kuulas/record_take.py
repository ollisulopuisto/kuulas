"""What the editor decides about a recorder take (WP12a part B), with no I/O but the
small plan file.

The recorder (``kuulas_recorder``, docs/RECORDER.md) owns the audio files and the
take's snapshot ``<take>.take.json``. The editor only reads them, so everything here
is a function of that snapshot: which take name comes next, when a take is ready to
import, where its clips go on the timeline, and how the recorder's events and error
keys become catalog keys. ``record_session`` does the talking and the committing.

The one file the editor writes beside a take is ``<take>.editor.json`` (the plan:
where on the timeline and on which track the take was asked to go), written before the
recorder starts, so an editor that crashes mid-take still knows where to put it.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from kuulas_recorder.client import segment_file  # the one place file names are built

from .take_names import take_name, unique_file_names

#: The folder inside the project package that holds the takes (owner, 2026-10-19).
RECORDINGS = "recordings"
SIDECAR_SUFFIX = ".take.json"
PLAN_SUFFIX = ".editor.json"

#: The recorder refuses names with other characters (``kuulas_recorder.names``: letters
#: of any script, digits, space and ``- _ . , ( ) ' + &``, at most 80, no leading dot or
#: space, no ``~``). The take adds ``"Take NNN-"`` in front, so the channel's part stays
#: well under the limit.
_ALLOWED = re.compile(r"[^\w .,()'+&-]|_", re.UNICODE)
MAX_CHANNEL = 40
#: A channel name when the track's name has nothing the recorder takes (a file-name
#: token, never shown as text).
FALLBACK_CHANNEL = "Mic"


def channel_name(track_name: str) -> str:
    """The track name as the recorder accepts it for a channel (it becomes part of the
    file name ``<take>-<channel>.wav``)."""
    name = _ALLOWED.sub("", track_name or "")
    name = re.sub(r"\s+", " ", name).strip()[:MAX_CHANNEL]
    name = name.lstrip(" .-,()'+&").rstrip(" .")
    return name or FALLBACK_CHANNEL


def takes_in(file_names: list[str]) -> list[str]:
    """The takes whose snapshot is among ``file_names``, sorted."""
    return sorted(n[: -len(SIDECAR_SUFFIX)] for n in file_names
                  if n.endswith(SIDECAR_SUFFIX))


def unique_channel_names(names: list[str]) -> list[str]:
    """The channel names of one take made distinct (case-insensitively: the files are
    ``<take>-<channel>.wav``, and macOS disks do not tell ``Host`` from ``host``).
    The second ``Host`` becomes ``Host 2``."""
    seen: set[str] = set()
    out = []
    for name in names:
        candidate, n = name, 1
        while candidate.lower() in seen:
            n += 1
            candidate = f"{name} {n}"
        seen.add(candidate.lower())
        out.append(candidate)
    return out


def next_take(file_names: list[str], channels: str | list[str], when: datetime) -> str:
    """``"Take N"`` one above every take number among the folder's files, and never a
    name whose files would collide with one there (case-insensitive: macOS disks).
    ``channels``: the channel names of the take (one name, or a list)."""
    names = [channels] if isinstance(channels, str) else list(channels)
    used = list(file_names)
    taken = {n.lower() for n in file_names}
    while True:
        take = take_name(used, when)
        wavs = [segment_file(take, name, 1)[:-4] for name in names]
        free = all(unique_file_names([wav], file_names) == [wav + ".wav"] for wav in wavs)
        if free and (take + SIDECAR_SUFFIX).lower() not in taken:
            return take
        used.append(take)


def readiness(sidecar: dict, *, running: bool) -> str | None:
    """``"import"`` when the take is over (``stopped``, or ``interrupted`` and repaired),
    ``"running"`` while a recorder writes it, ``"repair"`` when it says ``recording``
    but no recorder does (a crash: the recorder's ``repair`` comes first), else None."""
    state = sidecar.get("state")
    if state in ("stopped", "interrupted"):
        return "import"
    if state == "recording":
        return "running" if running else "repair"
    return None


@dataclass(frozen=True)
class ClipPlan:
    file: str  # in the recordings folder
    start: int  # timeline frame
    segment: int
    offset: int = 0  # frames cut from the head of the file (pre-roll before the timeline)


def _channel(sidecar: dict, channel: int | None = None) -> str | None:
    """The recorder's name for device channel ``channel`` (the take's first channel when
    None); None when the take has no such channel."""
    channels = sidecar.get("channels") or []
    if channel is None:
        return channels[0].get("name") if channels else None
    return next((c.get("name") for c in channels if c.get("channel") == channel), None)


def clip_plan(sidecar: dict, at: int, on_disk: set[str] | None = None,
              channel: int | None = None) -> list[ClipPlan]:
    """One clip per segment of one channel of the take (``channel``: the device channel
    number; the take's first channel when None), at ``at`` plus the segment's place on
    the take's clock. A file with no frames (the snapshot's count, or absent from
    ``on_disk`` when given) and a segment with no known start make no clip. Every
    channel of a take shares the clock, so the clips of different channels line up.

    Pre-roll (WP12c): the take's clock starts ``preroll_frames`` before Record was
    pressed, so the take is placed that much earlier and the pre-roll ends at ``at``.
    What would fall before the start of the timeline is cut from the clip's head
    (``offset``); a segment that lies wholly in the cut part makes no clip."""
    if at < 0:
        msg = f"at must not be negative, got {at}"
        raise ValueError(msg)
    name = _channel(sidecar, channel)
    preroll = max(0, int(sidecar.get("preroll_frames") or 0))
    plans: list[ClipPlan] = []
    for seg in sorted(sidecar.get("segments") or [], key=lambda s: s.get("segment", 0)):
        entry = (seg.get("files") or {}).get(name) if name else None
        if entry is None or seg.get("start_frame") is None:
            continue
        has_audio = (entry["file"] in on_disk) if on_disk is not None else (
            entry.get("frames", 0) > 0)
        if not has_audio:
            continue
        start = at + int(seg["start_frame"]) - preroll
        cut = max(0, -start)
        if cut and cut >= int(entry.get("frames", 0)) > 0:
            continue  # nothing of this segment lies on the timeline
        plans.append(ClipPlan(entry["file"], max(0, start), int(seg["segment"]), cut))
    return plans


def summary(sidecar: dict) -> dict:
    """What the user is told about a take besides its clips."""
    gaps = sidecar.get("gaps") or []
    return {"interrupted": sidecar.get("state") == "interrupted",
            "gaps": len(gaps), "gap_frames": sum(int(g.get("frames", 0)) for g in gaps),
            "dropouts": len(sidecar.get("dropouts") or []),
            "overflows": int(sidecar.get("overflows") or 0),
            "worker_restarts": int(sidecar.get("worker_restarts") or 0),
            "failed_channels": [str(c.get("name", ""))
                                for c in sidecar.get("failed_channels") or []],
            "frames": int(sidecar.get("frames") or 0)}


# -- the plan file -----------------------------------------------------------------


@dataclass(frozen=True)
class Lane:
    """One recorded channel and where it goes (WP12b)."""

    channel: int  # the device's channel, 1-based
    name: str  # the recorder's name for it (part of the file name)
    track_id: str | None  # None: a new speech track named track_name
    track_name: str


@dataclass(frozen=True)
class TakePlan:
    take: str
    at: int  # the timeline frame the take starts at
    track_id: str | None  # None: a new speech track named track_name
    track_name: str
    channel: int
    device: dict = field(default_factory=dict)
    #: Every channel of the take; empty for a plan written before WP12b, which is one
    #: lane made of the fields above (``all_lanes``). Those fields stay the first lane's.
    lanes: tuple[Lane, ...] = ()

    @property
    def all_lanes(self) -> tuple[Lane, ...]:
        return self.lanes or (Lane(self.channel, channel_name(self.track_name),
                                   self.track_id, self.track_name),)


def plan_path(folder: Path, take: str) -> Path:
    return folder / f"{take}{PLAN_SUFFIX}"


def write_plan(folder: Path, plan: TakePlan) -> None:
    """Written whole (temporary file, fsync, rename): read back after a crash."""
    path = plan_path(folder, plan.take)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(asdict(plan), f)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def read_plan(folder: Path, take: str) -> TakePlan | None:
    try:
        text = plan_path(folder, take).read_text(encoding="utf-8")
        if len(text) > 256 * 1024:
            return None
        raw = json.loads(text)
        if not isinstance(raw, dict):
            return None

        take_val = str(raw["take"])[:1024]
        raw_tid = raw.get("track_id")
        track_id = str(raw_tid)[:1024] if raw_tid is not None else None
        track_name = str(raw.get("track_name") or take_val)[:1024]
        channel = int(raw.get("channel", 1))

        device = raw.get("device")
        if not isinstance(device, dict):
            device = {}

        lanes = []
        for lane in raw.get("lanes") or []:
            if not isinstance(lane, dict):
                continue
            raw_ltid = lane.get("track_id")
            l_track_id = str(raw_ltid)[:1024] if raw_ltid is not None else None
            lanes.append(Lane(
                channel=int(lane["channel"]),
                name=str(lane["name"])[:1024],
                track_id=l_track_id,
                track_name=str(lane.get("track_name", ""))[:1024]
            ))

        return TakePlan(take=take_val, at=int(raw["at"]), track_id=track_id,
                        track_name=track_name, channel=channel,
                        device=device, lanes=tuple(lanes))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def remove_plan(folder: Path, take: str) -> None:
    with contextlib.suppress(OSError):
        plan_path(folder, take).unlink()


# -- events and errors into catalog keys -----------------------------------------------

#: The recorder's stable error keys (docs/RECORDER.md, "Error keys"); each has
#: ``error.record.<key>`` in the catalogs. Anything else is ``error.record.other``.
RECORDER_ERRORS = (
    "bad_request", "unknown_command", "bad_name", "already_recording", "not_recording",
    "busy", "take_exists", "folder_not_writable", "disk_full", "device_list_failed",
    "device_not_found", "channels_unavailable", "device_rate_mismatch",
    "device_open_failed", "device_no_audio", "file_exists", "worker_failed",
    "take_not_found", "internal", "timeout", "disconnected", "spawn_failed",
    "other", "unavailable", "hold_required", "another_project", "no_device",
    "bad_channel", "stop_gesture", "no_playback", "armed_mismatch", "same_track",
    "old_recorder",
)


def error_key(recorder_key: str) -> str:
    return f"error.record.{recorder_key if recorder_key in RECORDER_ERRORS else 'other'}"


#: Every catalog key ``event_notice`` can answer.
EVENT_KEYS = (
    "record.event.disk_low", "record.event.input_overflow", "record.event.dropout",
    "record.event.device_lost", "record.event.device_back", "record.event.gap",
    "record.event.worker_restarted", "record.event.disk_full",
    "record.event.channel_failed",
    "record.event.worker_keeps_failing", "record.event.error", "record.event.disarmed",
)


def _seconds(frames: int, rate: int) -> str:
    return f"{frames / rate:.1f}"


#: ``(event, key)`` -> ``(catalog key, level, params of the event)``; ``key`` is None
#: for events that have none. ``level``: ``alarm`` (the take is in danger), ``warning``
#: or ``info``.
_NOTICES = {
    ("warning", "disk_low"): (
        "record.event.disk_low", "warning",
        lambda e, _r: {"minutes": int(e.get("seconds_left", 0)) // 60}),
    ("warning", "input_overflow"): ("record.event.input_overflow", "warning",
                                    lambda e, _r: {"count": int(e.get("count", 1))}),
    ("warning", "dropout"): (
        "record.event.dropout", "warning",
        lambda e, r: {"seconds": _seconds(int(e.get("frames", 0)), r)}),
    # One channel's file failed; the others go on (WP12b).
    ("warning", "channel_failed"): ("record.event.channel_failed", "alarm",
                                    lambda e, _r: {"name": str(e.get("name", ""))}),
    ("device_lost", None): ("record.event.device_lost", "alarm",
                            lambda e, _r: {"device": _device(e)}),
    ("device_back", None): ("record.event.device_back", "info",
                            lambda e, _r: {"device": _device(e)}),
    ("gap", None): ("record.event.gap", "warning",
                    lambda e, r: {"seconds": _seconds(int(e.get("frames", 0)), r)}),
    ("worker_restarted", None): ("record.event.worker_restarted", "warning",
                                 lambda e, _r: {"count": int(e.get("restarts", 1))}),
    # Only a listener that was lost is news; the user's own disarm, a replaced listener
    # and the time-to-live running out are not (``event_notice`` filters them).
    ("disarmed", None): ("record.event.disarmed", "warning", lambda _e, _r: {}),
    ("error", "disk_full"): ("record.event.disk_full", "alarm", lambda _e, _r: {}),
    ("error", "worker_keeps_failing"): ("record.event.worker_keeps_failing", "alarm",
                                        lambda _e, _r: {}),
}


def _device(event: dict) -> str:
    return str((event.get("device") or {}).get("name", ""))


def event_notice(event: dict, rate: int) -> dict | None:
    """A recorder event as ``{key, params, level}`` for the record view, or None for an
    event that is not a message (levels, started, stopped: the view shows those, and
    warnings of a kind this version does not know)."""
    kind = event.get("event")
    if kind == "disarmed" and event.get("reason") not in ("device_lost", "worker_died"):
        return None
    sub = event.get("key") if kind in ("warning", "error") else None
    found = _NOTICES.get((kind, sub))
    if found is None:
        if kind != "error":
            return None
        return {"key": "record.event.error", "level": "alarm",
                "params": {"detail": str(event.get("text", ""))}}
    key, level, params = found
    return {"key": key, "level": level, "params": params(event, rate)}
