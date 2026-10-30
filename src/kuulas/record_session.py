"""The editor's side of recording (WP12a part B): a viewer and a remote for the recorder.

The recorder is its own program (``kuulas_recorder``, docs/RECORDER.md). The editor
talks to it only through ``kuulas_recorder.client`` and never imports anything else of
it. What that buys, and what this module keeps true:

- **A stuck or crashed editor never stops a take.** Commands use short connections of
  their own; one long connection (the watcher thread) hears the events. Closing this
  object closes the connections and nothing else; a reopened editor finds the take
  running (``hello``) and shows it again.
- **The recorder missing is an error with a key, not a crash.** ``devices`` and
  ``start`` start it (``spawn_supervisor``) when nobody answers; when that fails too
  the answer is ``error.record.unavailable`` and the editor works on.
- **A take is imported once it is over**: on its ``stopped`` event or the answer to
  ``stop``; one clip per segment at the segment's place on the take's clock, linked in
  place in ``recordings/``, in one undo step (``Session.import_take``).
- **A take left behind by a crash is offered, never imported silently**: ``pending``
  lists the takes in ``recordings/`` that no media of the project links to; the editor
  shows them in a notice with one Import button.
- **No listening while recording** (owner, 2026-10-19): the record view says monitoring
  is the interface's job; the server stops playback when a take starts.

Levels and events go out through ``publish`` (the live channel's hub) as
``{"type": "record", "kind": ...}`` frames: ``status``, ``level``, ``notice``,
``imported``, ``pending``. The page never polls.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import shutil
import socket
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from kuulas_recorder.client import (
    PROTOCOL,
    RecorderClient,
    RecorderError,
    spawn_supervisor,
)

from . import disk_budget, ops
from . import record_take as rt
from .messages import KuulasError, t
from .preview_level import PEAK_TO_LUFS_DB
from .record_loudness import RecordingLoudness

log = logging.getLogger("kuulas.record")

#: The hold of the "hold 2 s" stop preference: the server checks it too.
HOLD_MS = 2000
#: The stop gestures the page may report (owner, 2026-10-19: two steps by default; one
#: click, or the 2 s hold, by preference).
STOP_MODES = ("two_step", "one_click", "hold")
#: How long the watcher waits before it tries the recorder again when nobody answers.
RETRY_S = 2.0
#: The notices of the take kept for a page that opens mid-take.
NOTICES_KEPT = 50
#: Bytes per sample of the recorder's files (24-bit PCM), for the disk estimate.
BYTES_PER_SAMPLE = 3
#: How long ``stop`` may take: the recorder answers once every file is closed.
STOP_TIMEOUT_S = 60.0
#: The recorder's states while it listens for pre-roll without recording (WP12c).
ARMED_STATES = ("arming", "armed", "disarming")
#: The longest pre-roll the recorder accepts (``kuulas_recorder.supervisor``).
MAX_PREROLL_S = 600
#: Most channels one take records (a big interface; the recorder has no limit of its own).
MAX_CHANNELS = 64


def _channel_numbers(asked: object) -> list[int]:
    """Device channel numbers from the page: whole numbers from 1, distinct, at most
    ``MAX_CHANNELS``; anything else is ``error.record.bad_channel``. Sorted: the order
    the recorder lists, meters and compares them in."""
    if (not isinstance(asked, list) or not asked or len(asked) > MAX_CHANNELS
            or any(not isinstance(c, int) or isinstance(c, bool) or c < 1 for c in asked)
            or len(set(asked)) != len(asked)):
        raise RecordError("error.record.bad_channel", channel=asked)
    return sorted(asked)


class RecordError(KuulasError):
    """A recording request that cannot be done; ``status`` is the HTTP status."""

    def __init__(self, key: str, /, status: int = 400, **params) -> None:
        super().__init__(key, **params)
        self.status = status


#: Recorder error keys that mean "not now" (409) rather than "wrong request" (400).
_CONFLICT = {"already_recording", "busy", "not_recording", "take_exists",
             "another_project", "armed_mismatch"}
_UNAVAILABLE = {"timeout", "disconnected", "spawn_failed", "unavailable"}


def _status_code(key: str) -> int:
    if key in _UNAVAILABLE:
        return 503
    if key in _CONFLICT:
        return 409
    return 400


def default_connect() -> RecorderClient:
    if not hasattr(socket, "AF_UNIX"):
        raise OSError
    return RecorderClient.connect(timeout=20.0)


def default_spawn() -> None:
    spawn_supervisor()


class RecordSession:
    """One per open project. ``connect`` and ``spawn`` are injectable for tests."""

    def __init__(self, session, publish: Callable[[dict], None] | None = None, *,
                 connect: Callable[[], RecorderClient] = default_connect,
                 spawn: Callable[[], None] = default_spawn, retry_s: float = RETRY_S,
                 hold_ms: int = HOLD_MS, watch: bool = True) -> None:
        self.session = session
        # While a take of this project records, the session refuses edits (Session.
        # _check_not_recording); the answer is read live from the last status heard.
        if hasattr(session, "editing_paused"):
            session.editing_paused = self.editing_paused
        # Absolute: the recorder refuses a relative folder (`kuulas open Show.kuulas`).
        self.folder = (Path(session.package.path) / rt.RECORDINGS).resolve()
        self.publish = publish if publish is not None else (lambda _m: None)
        self._connect = connect
        self._spawn = spawn
        self.retry_s = retry_s
        self.hold_ms = hold_ms
        self._lock = threading.Lock()  # the recorder's status as last heard
        self._import_lock = threading.Lock()  # one import at a time
        self._status: dict = {"state": "idle"}
        #: The track clips played from the cart are put on during the take (set at Start).
        self._cart_track: str | None = None
        self._cart_ids: list[str] = []
        self._cart_issued: set[tuple[str, ...]] = set()
        self._cart_base = 0
        self._cart_preroll = 0
        self._voice_levels: deque = deque()
        self._cart_lock = threading.RLock()
        self._available = False
        self._position = 0
        self._notices: deque = deque(maxlen=NOTICES_KEPT)
        #: Takes this editor imported (or found empty) -> what the import reported.
        self._imported: dict[str, dict | None] = {}
        self._we_armed = False  # this editor armed the recorder (pre-roll)
        self._input_loudness = RecordingLoudness(
            enabled=watch and hasattr(socket, "AF_UNIX"))
        self._channels_hint = 1  # channels the next take would record (disk estimate)
        self._closed = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        if watch and hasattr(socket, "AF_UNIX"):
            self._thread = threading.Thread(target=self._watch,
                                            name="kuulas-record-watch", daemon=True)
            self._thread.start()

    def set_publish(self, publish: Callable[[dict], None]) -> None:
        self.publish = publish

    def close(self) -> None:
        """Stop listening. A take that is recording goes on (that is the point); a
        microphone this editor armed for pre-roll is let go (the recorder would also do
        it itself once nobody keeps it armed)."""
        self._closed.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._input_loudness.close()
        if self._we_armed:
            self._we_armed = False
            with contextlib.suppress(RecordError):
                self._command("disarm", timeout=5.0)

    # -- talking to the recorder ------------------------------------------------

    def _client(self, spawn: bool) -> RecorderClient:
        try:
            return self._connect()
        except (OSError, RecorderError) as e:
            if not spawn:
                raise RecordError("error.record.unavailable", status=503) from e
        try:
            self._spawn()
            client = self._connect()
        except (OSError, RecorderError) as e:
            log.warning("the recorder could not be started: %s", e)
            raise RecordError("error.record.unavailable", status=503) from e
        self._wake.set()  # the watcher connects at once, not after its pause
        return client

    def _command(self, cmd: str, *, spawn: bool = False, timeout: float | None = None,
                 **args) -> dict:
        client = self._client(spawn)
        try:
            return client.request(cmd, timeout=timeout, **args)
        except RecorderError as e:
            raise RecordError(rt.error_key(e.key), status=_status_code(e.key),
                              detail=e.text, **self._error_params(e.key, args)) from e
        finally:
            client.close()

    def _error_params(self, key: str, args: dict) -> dict:
        """What the translated message needs besides the recorder's English text."""
        if key == "device_rate_mismatch":
            return {"rate": args.get("rate", self.rate)}
        return {}

    @property
    def rate(self) -> int:
        return self.session.state.rate

    # -- what the page asks -----------------------------------------------------

    def devices(self) -> list[dict]:
        """The input devices, from the recorder (started if need be)."""
        found = self._command("devices", spawn=True)["devices"]
        return [{"index": d["index"], "name": d["name"], "channels": d["channels"],
                 "default_rate": d.get("default_rate"), "default": bool(d.get("default"))}
                for d in found]

    def _ours(self, status: dict) -> bool:
        folder = status.get("folder")
        if not folder:
            return False
        try:
            return Path(folder).resolve() == self.folder.resolve()
        except OSError:
            return False

    def _recording(self, status: dict) -> bool:
        # Listening for pre-roll (armed) is not recording: nothing is written.
        return status.get("state", "idle") not in ("idle", None, *ARMED_STATES)

    def editing_paused(self) -> bool:
        """Does a take of THIS project record (as last heard)? Listening for pre-roll and
        another project's take do not count."""
        with self._lock:
            return self._recording(self._status) and self._ours(self._status)

    def recording_now(self) -> bool:
        """Is a take recording, as last heard (no question to the recorder: playback asks
        this on every play)? Any take counts: a speaker playing into a live microphone
        is what the owner's "no listening while recording" rule keeps out."""
        with self._lock:
            return self._recording(self._status)

    def _disk(self, status: dict, channels: int = 1) -> dict:
        """Recording time left: the recorder's estimate while a take runs, else ours
        (for ``channels`` channels: each is a file of its own)."""
        left = (status.get("disk") or {}).get("seconds_left")
        if left is None:
            try:
                where = self.folder if self.folder.exists() else self.folder.parent
                free = shutil.disk_usage(where).free
                left = disk_budget.seconds_left(free, self.rate, max(1, channels),
                                         BYTES_PER_SAMPLE)
            except (OSError, ValueError):
                return {"seconds_left": None, "state": "ok", "text": ""}
        left = max(0, int(left))
        return {"seconds_left": left, "state": disk_budget.disk_state(left),
                "text": disk_budget.format_hm(left)}

    def status(self, channels: int | None = None) -> dict:
        """Everything the record view shows, asked of the recorder afresh (never
        started for this: looking must not launch anything). ``channels``: how many the
        next take would record, for the disk estimate before a take runs (remembered
        for the status frames the watcher publishes)."""
        if channels is not None:
            self._channels_hint = max(1, int(channels))
        try:
            status = self._command("status", timeout=5.0)
            available = True
        except RecordError:
            status, available = {"state": "idle"}, False
        with self._lock:
            self._status, self._available = status, available
            if "position_frames" in status:
                self._position = int(status["position_frames"])
        return self._view(status, available)

    def _view(self, status: dict, available: bool) -> dict:
        ours = self._ours(status)
        recording = self._recording(status)
        take = status.get("take") if recording else None
        plan = rt.read_plan(self.folder, take) if (take and ours) else None
        armed = status.get("state") == "armed"
        if recording and ours and take:
            names = [str(channel.get("name", ""))
                     for channel in status.get("channels", [])]
            if not names and plan:
                names = [lane.name for lane in plan.all_lanes]
            self._input_loudness.observe(self.folder, take, self.rate, names)
        else:
            self._input_loudness.reset()
        return {
            "short_term_lufs": self._input_loudness.read(),
            "available": available,
            "state": status.get("state", "idle"),
            "recording": recording,
            # Listening into the pre-roll buffer, nothing written (the page says so).
            "armed": armed,
            "preroll_s": (status.get("armed") or {}).get("preroll_s") if armed else None,
            # The channels being listened to, in the order the level frames list them.
            "armed_channels": list((status.get("armed") or {}).get("channels") or [])
            if armed else [],
            # The channels of the take that records now: {channel, name}.
            "channels": list(status.get("channels") or []) if recording else [],
            "preroll_frames": int(status.get("preroll_frames") or 0) if recording else 0,
            "ours": ours,
            "elsewhere": recording and not ours,
            "take": take,
            "position_frames": self._position if recording else 0,
            "rate": self.rate,
            "start_utc": status.get("start_utc") if recording else None,
            "device": status.get("device") if recording else None,
            "plan": None if plan is None else {
                "track_id": plan.track_id, "track_name": plan.track_name,
                "at": plan.at, "channel": plan.channel,
                "lanes": [asdict(lane) for lane in plan.all_lanes]},
            "disk": self._disk(status if recording else {}, self._channels_hint),
            "gaps": len(status.get("gaps") or []) if isinstance(status.get("gaps"), list)
            else int(status.get("gaps") or 0),
            "notices": list(self._notices) if (recording and ours) else [],
            "pending": self.pending(running_take=take if ours else None),
            "hold_ms": self.hold_ms,
        }

    def arm(self, *, device: dict | None, preroll_s: float, channel: int | None = None,
            channels: list[int] | None = None) -> dict:
        """Listen for pre-roll (WP12c): the recorder opens the input and keeps the last
        ``preroll_s`` seconds of every channel in memory, writing nothing, so a take
        started next begins that long before Record was pressed. Arming again with the
        same settings only keeps it armed (the recorder lets go by itself when nobody
        does). ``channels`` (device channel numbers; ``channel`` is the one-channel
        form) must be the ones the take will record."""
        if self.session.read_only:
            holder = self.session.package.locked_by or {}
            raise ops.EditError("error.history.read_only", host=holder.get("host", "?"))
        if channels is None:
            channels = [channel if channel is not None else 1]
        wanted = _channel_numbers(channels)
        if (not isinstance(preroll_s, (int, float)) or isinstance(preroll_s, bool)
                or not 0 < preroll_s <= MAX_PREROLL_S):
            raise RecordError("error.record.bad_request", detail="preroll_s")
        args = {"channels": wanted, "rate": self.rate, "preroll_s": float(preroll_s)}
        if device:
            args["device"] = {"index": device.get("index"), "name": device.get("name")}
        self._ensure_current_recorder()
        answer = self._command("arm", spawn=True, **args)
        self._we_armed = True
        return self._publish_answer(answer)

    def _ensure_current_recorder(self) -> None:
        """A recorder outlives the editor, so a new editor may meet an older one that
        lacks a command it needs (``arm``). Idle (or only listening, which writes
        nothing), it is asked to exit and the caller's next command starts a fresh one.
        Recording, it is never touched (rule 17): the take goes on and the caller is
        told, so pre-roll waits for a recorder that is new."""
        try:
            hello = self._command("hello", timeout=5.0)
        except RecordError:
            return  # nobody there: the next command starts a current one
        if int(hello.get("protocol") or 0) >= PROTOCOL:
            return
        state = (hello.get("status") or {}).get("state", "idle")
        if state not in ("idle", *ARMED_STATES):
            raise RecordError("error.record.old_recorder", status=409)
        try:
            self._command("quit", timeout=5.0)
        except RecordError as e:  # a take began in between: leave it alone
            raise RecordError("error.record.old_recorder", status=409) from e
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            try:
                self._connect().close()
            except (OSError, RecorderError):
                return  # gone
            time.sleep(0.05)

    def disarm(self) -> dict:
        """Stop listening and drop the buffer. Harmless when not armed."""
        answer = self._command("disarm", timeout=20.0)
        self._we_armed = False
        return self._publish_answer(answer)

    def _publish_answer(self, answer: dict) -> dict:
        with self._lock:
            self._status, self._available = answer, True
        view = self._view(answer, True)
        self.publish({"type": "record", "kind": "status", "status": view})
        return view

    def _lanes(self, channels: list[dict] | None, channel: int | None,
               track_id: str | None, name: str) -> list[rt.Lane]:
        """What the page asked as lanes, in device-channel order (the order the recorder
        lists and meters them, and the order an armed recorder compares). A new track
        left unnamed is "Channel N" when several channels are recorded; a single one
        stays unnamed here and is named after the take once it has a number."""
        asked = channels if channels is not None else [
            {"channel": channel if channel is not None else 1, "track_id": track_id,
             "name": name}]
        raw = [c.get("channel") if isinstance(c, dict) else None for c in asked]
        _channel_numbers(raw)  # refuses nonsense with a key before anything else
        lanes = []
        used_tracks: set[str] = set()
        for number, c in sorted(zip(raw, asked, strict=True), key=lambda x: x[0]):
            tid = c.get("track_id")
            if tid == "new":
                tid = None
            if tid is not None:
                if tid in used_tracks:
                    raise RecordError("error.record.same_track")
                used_tracks.add(tid)
                track_name = ops._find_track(self.session.state, tid).name
            else:
                track_name = (c.get("name") or "").strip()
                if not track_name and len(asked) > 1:
                    track_name = t("record.channel_track", n=number)
            lanes.append(rt.Lane(channel=number, name="", track_id=tid,
                                 track_name=track_name))
        labels = rt.unique_channel_names([rt.channel_name(lane.track_name)
                                          for lane in lanes])
        return [replace(lane, name=label)
                for lane, label in zip(lanes, labels, strict=True)]

    def start(self, *, device: dict | None, at: int, channels: list[dict] | None = None,
              channel: int | None = None, track_id: str | None = None,
              name: str = "", cart_track: str | None = None,
              latency_ms: float = 0.0) -> dict:
        """Record a take into this project's ``recordings/``. ``channels``: one
        ``{channel, track_id, name}`` per device channel to record (WP12b), each onto
        its own track (``track_id`` None or ``"new"``: a new speech track named
        ``name``). ``channel``/``track_id``/``name`` are the one-channel form."""
        if self.session.read_only:
            holder = self.session.package.locked_by or {}
            raise ops.EditError("error.history.read_only", host=holder.get("host", "?"))
        lanes = self._lanes(channels, channel, track_id, name)
        cart_track = cart_track or None
        # The delay between what the performer heard and what was captured (a manual
        # figure for now): cut from the take's head when it lands. 0 to 2 s.
        delay_s = min(max(float(latency_ms or 0), 0.0), 2000.0) / 1000
        latency_frames = round(delay_s * self.rate)
        if cart_track is not None and cart_track != "new":
            ops._find_track(self.session.state, cart_track)  # unknown: an EditError
            if cart_track in {lane.track_id for lane in lanes}:
                raise RecordError("error.record.cart_track_records")
        if at < 0:
            raise RecordError("error.record.bad_request", detail="at")
        self.folder.mkdir(parents=True, exist_ok=True)
        for _attempt in range(3):  # another take may appear in between: next number
            take = rt.next_take(os.listdir(self.folder), [lane.name for lane in lanes],
                                datetime.now(UTC))
            plan_lanes = tuple(replace(lane, track_name=lane.track_name or take)
                               for lane in lanes)
            first = plan_lanes[0]
            plan = rt.TakePlan(take=take, at=int(at), track_id=first.track_id,
                               track_name=first.track_name, channel=first.channel,
                               device=dict(device or {}), lanes=plan_lanes,
                               latency_frames=latency_frames)
            # Before the recorder starts: a crash a moment later still knows the place.
            rt.write_plan(self.folder, plan)
            args = {"folder": str(self.folder), "take": take,
                    "channels": [lane.channel for lane in plan_lanes],
                    "names": [lane.name for lane in plan_lanes], "rate": self.rate}
            if device:
                args["device"] = {"index": device.get("index"),
                                  "name": device.get("name")}
            try:
                answer = self._command("start", spawn=True, **args)
            except RecordError as e:
                rt.remove_plan(self.folder, take)
                if e.key == "error.record.take_exists":
                    continue
                raise
            with self._lock:
                self._status, self._available = answer, True
                self._position = int(answer.get("position_frames", 0))
                self._notices.clear()
            self._make_tracks(plan, cart_track)
            view = self._view(answer, True)
            self.publish({"type": "record", "kind": "status", "status": view})
            if answer.get("warning"):
                self._notice(answer["warning"] | {"event": "warning"})
            return view
        raise RecordError("error.record.take_exists", status=409, detail="")

    def _make_tracks(self, plan: rt.TakePlan, cart_track: str | None = None) -> None:
        """Make the new tracks of a take that has started (a lane with no track yet), in
        one undo step, and write their ids into the plan: the take is then drawn on them
        live and lands on them. Never stops the take: when it fails the lanes stay "new"
        and the tracks are made when the take lands, as before."""
        new = [lane for lane in plan.all_lanes if lane.track_id is None]
        self._voice_levels.clear()
        self._cart_track = None if cart_track == "new" else cart_track
        if not new and cart_track != "new":
            return
        ids = {lane.channel: ops.new_id("t") for lane in new}
        specs = [(ids[lane.channel], lane.track_name) for lane in new]
        if cart_track == "new":
            self._cart_track = ops.new_id("t")
            specs.append((self._cart_track, t("record.cart_track"), False))
        try:
            self.session.add_take_tracks(specs)
        except Exception as e:  # noqa: BLE001 - the take must go on whatever this says
            log.warning("tracks for take %s were not made: %s", plan.take, e)
            if cart_track == "new":
                self._cart_track = None
            return
        if not new:
            return
        lanes = tuple(replace(lane, track_id=ids.get(lane.channel, lane.track_id))
                      for lane in plan.all_lanes)
        first = lanes[0]
        rt.write_plan(self.folder, replace(plan, track_id=first.track_id, lanes=lanes))

    def take_track_ids(self, take: str) -> list[str]:
        """The tracks the take records onto (the ids the plan holds once the new ones are
        made); empty when the plan cannot be read."""
        plan = rt.read_plan(self.folder, take)
        if plan is None:
            return []
        return [lane.track_id for lane in plan.all_lanes if lane.track_id]

    def cart_log(self, entry_id: str, *, gain_db: float = 0) -> dict:
        """A clip played from the cart during this take: put it on the cart track where
        the take is now (take start + what was recorded, the pre-roll not counted), so
        the question sits where it was asked. ``RecordError`` when no take of this project
        records or no cart track was chosen at Start."""
        with self._lock:
            status, position = self._status, self._position
            recording = self._recording(status) and self._ours(status)
            track_id = self._cart_track
        if not recording:
            raise RecordError("error.record.not_recording", status=409)
        if track_id is None:
            raise RecordError("error.record.no_cart_track", status=409)
        plan = rt.read_plan(self.folder, status.get("take") or "")
        base = 0 if plan is None else plan.at
        preroll = max(0, int(status.get("preroll_frames") or 0))
        at = base + max(0, position - preroll)
        with self._cart_lock:
            self._end_cart()
            result = self.session.cart_log(entry_id, at=at, track_id=track_id,
                                           gain_db=gain_db)
            self._cart_ids = result.get("clip_ids", [])
            self._cart_issued.add(tuple(self._cart_ids))
            self._cart_base, self._cart_preroll = base, preroll
            return {"at": at, "track_id": track_id, "clip_ids": self._cart_ids}

    def _end_cart(self) -> None:
        if self._cart_ids:
            stop = self._cart_base + max(0, self._position - self._cart_preroll)
            self.session.cart_end(self._cart_ids, stop)
            self._cart_ids = []

    def _take_cart_end(self, take: str) -> None:
        # A stopped event has sample counts, not position_frames. Segment offsets
        # retain the take clock across gaps; a total of samples would erase gaps.
        with self._cart_lock:
            sidecar = self._sidecar(take) or {}
            ends = [int(seg["start_frame"]) + int(file.get("frames", 0))
                    for seg in sidecar.get("segments", [])
                    if seg.get("start_frame") is not None
                    for file in (seg.get("files") or {}).values()]
            if ends:
                self._position = max(self._position, *ends)
            self._end_cart()

    def cart_end(self, clip_ids: list[str] | None = None) -> None:
        """Only the current play's exact IDs can end it; stale ends are harmless."""
        with self._cart_lock:
            if clip_ids is not None and clip_ids != self._cart_ids:
                if tuple(clip_ids) in self._cart_issued:
                    return
                raise RecordError("error.record.bad_request", detail="clip_ids")
            self._end_cart()

    def cart_preview(self, entry_id: str, trim: float = 0):
        """Recent voices: power mean of non-silent channel peaks over three seconds,
        minus the preview's 14 dB peak-to-LUFS estimate. No voices: project reference.
        """
        now = time.monotonic()
        with self._lock:
            levels = [v for when, v in self._voice_levels if now - when <= 3]
        voice = (10 * math.log10(sum(10 ** (v / 10) for v in levels) / len(levels))
                 - PEAK_TO_LUFS_DB) if levels else None
        if self._cart_track is None:
            raise RecordError("error.record.no_cart_track", status=409)
        return self.session.clipboard_preview(entry_id, cart_voice=voice,
                                              cart_trim=trim, cart_track=self._cart_track)

    def stop(self, mode: str | None, held_ms: int = 0) -> dict:
        """Stop the take, then import it. ``mode`` is the user's stop gesture
        (``two_step``, the default; ``one_click``; ``hold``): a request without one, or a
        hold shorter than 2 s, is refused, so a stray call from other UI code cannot stop
        a take."""
        if mode not in STOP_MODES:
            raise RecordError("error.record.stop_gesture")
        if mode == "hold" and held_ms < self.hold_ms:
            raise RecordError("error.record.hold_required", seconds=self.hold_ms / 1000)
        status = self.status()
        if not status["recording"]:
            raise RecordError("error.record.not_recording", status=409)
        if not status["ours"]:
            raise RecordError("error.record.another_project", status=409)
        answer = self._command("stop", timeout=STOP_TIMEOUT_S)
        take = (answer.get("take") or {}).get("take") or status["take"]
        self._take_cart_end(take)
        imported = self.import_take(take)
        self._cart_track = None
        self.publish({"type": "record", "kind": "status", "status": self.status()})
        return {"take": take, "imported": imported}

    # -- importing ----------------------------------------------------------------

    def _sidecar(self, take: str) -> dict | None:
        try:
            path = rt.take_path(self.folder, take, rt.SIDECAR_SUFFIX)
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _take_files(self, sidecar: dict) -> set[Path]:
        out = set()
        for seg in sidecar.get("segments") or []:
            for entry in (seg.get("files") or {}).values():
                out.add((self.folder / entry["file"]).resolve())
        return out

    def _is_imported(self, take: str, sidecar: dict, linked: set[Path]) -> bool:
        files = self._take_files(sidecar)
        return take in self._imported or bool(files and files & linked)

    def pending(self, running_take: str | None = None) -> list[dict]:
        """Takes in ``recordings/`` that the project has no clip media from, except the
        one recording now: after a crash, offered to the user (never imported unasked)."""
        try:
            names = os.listdir(self.folder)
        except OSError:
            return []
        linked = self.session.linked_files()
        out = []
        for take in rt.takes_in(names):
            sidecar = self._sidecar(take)
            if sidecar is None or take == running_take:
                continue
            ready = rt.readiness(sidecar, running=False)
            if ready is None or self._is_imported(take, sidecar, linked):
                continue
            out.append({"take": take, "state": sidecar.get("state"), "readiness": ready,
                        "seconds": round(rt.summary(sidecar)["frames"] / self.rate, 1)})
        return out

    def import_take(self, take: str) -> dict | None:
        """Put a finished (or crashed) take on the timeline; None when it is already
        there or has no audio. A take that still says ``recording`` while no recorder
        writes it is repaired first (by the recorder; when it cannot be reached the
        files are used as they are: each is a valid WAV up to its last flush)."""
        if not rt.valid_name(take):
            raise RecordError("error.record.bad_request", detail="take")
        with self._import_lock:
            sidecar = self._sidecar(take)
            if sidecar is None:
                raise RecordError("error.record.take_not_found", status=404, detail=take)
            linked = self.session.linked_files()
            if self._is_imported(take, sidecar, linked):
                # The stop answer and the stopped event both import: the second caller
                # gets the first one's result (None after a restart: nothing to report).
                return self._imported.get(take)
            if rt.readiness(sidecar, running=False) == "repair":
                status = self.status()
                if status["recording"] and status["ours"] and status["take"] == take:
                    raise RecordError("error.record.busy", status=409, detail=take)
                try:
                    self._command("repair", spawn=True, folder=str(self.folder),
                                  take=take)
                    sidecar = self._sidecar(take) or sidecar
                except RecordError as e:
                    log.warning("take %s used without a repair: %s", take, e)
            plan = rt.read_plan(self.folder, take) or rt.TakePlan(
                take=take, at=0, track_id=None, track_name=take, channel=1)
            on_disk = {n for n in os.listdir(self.folder)
                       if (self.folder / n).is_file()
                       and (self.folder / n).stat().st_size > 44}
            # A plan from before WP12b names no channel: it is the take's first.
            lanes = []
            for lane in plan.all_lanes:
                clips = rt.clip_plan(sidecar, plan.at, on_disk,
                                     channel=lane.channel if plan.lanes else None)
                if clips:
                    lanes.append((clips, lane))
            summary = rt.summary(sidecar)
            interrupted = sidecar.get("state") != "stopped"
            if not lanes:
                self._imported[take] = None
                return None
            clip_name = t("record.take_interrupted", name=take) if interrupted else take
            _, clip_ids = self.session.import_take_lanes(
                [([(self.folder / c.file, c.start, c.offset + plan.latency_frames)
                   for c in clips],
                  lane.track_id, lane.track_name) for clips, lane in lanes],
                clip_name=clip_name, take=take)
            dropout_frames = sum(
                int(dropout.get("frames", 0)) for dropout in sidecar.get("dropouts") or []
            )
            result = {**summary, "take": take, "clips": len(clip_ids),
                      "dropout_seconds": round(dropout_frames / self.rate, 1),
                      "replaced": list(self.session.last_take_replaced),
                      "clip_ids": clip_ids,
                      "start": min(c.start for cl, _ in lanes for c in cl),
                      "tracks": len(lanes), "interrupted": interrupted}
            self._imported[take] = result
            self.publish({"type": "record", "kind": "imported", **result})
            return result

    def _import_later(self, take: str) -> None:
        def run() -> None:
            try:
                self.import_take(take)
            except Exception:  # a failed import is logged; the files stay offered
                log.exception("importing take %s failed", take)
                self.publish({"type": "record", "kind": "pending",
                              "pending": self.pending()})
        threading.Thread(target=run, name="kuulas-record-import", daemon=True).start()

    # -- the watcher ----------------------------------------------------------------

    def _notice(self, event: dict) -> None:
        notice = rt.event_notice(event, self.rate)
        if notice is None:
            return
        self._notices.append(notice)
        self.publish({"type": "record", "kind": "notice", **notice})

    def _set_available(self, available: bool) -> None:
        with self._lock:
            changed = available != self._available
            self._available = available
        if changed:
            self.publish({"type": "record", "kind": "available", "available": available})

    def _watch(self) -> None:
        while not self._closed.is_set():
            try:
                client = self._connect()
            except (OSError, RecorderError):
                self._set_available(False)
                self._wake.wait(self.retry_s)
                self._wake.clear()
                continue
            try:
                self._listen(client)
            except RecorderError as e:
                log.info("the recorder connection ended: %s", e)
            finally:
                client.close()
            self._after_disconnect()

    def _listen(self, client: RecorderClient) -> None:
        hello = client.request("hello", subscribe=True, levels=True)
        status = hello.get("status") or {}
        with self._lock:
            self._status = status
        self._set_available(True)
        self.publish({"type": "record", "kind": "status",
                      "status": self._view(status, True)})
        recovered = [r for r in status.get("recovered") or []
                     if r.get("take") and self._ours(r)]
        if recovered:
            self.publish({"type": "record", "kind": "pending", "pending": self.pending()})
        while not self._closed.is_set():
            event = client.next_event(0.5)
            if event is None:
                if client.closed:
                    return
                continue
            self._on_event(event)

    def _on_event(self, event: dict) -> None:
        kind = event.get("event")
        with self._lock:
            ours = self._ours(self._status)
            armed = self._status.get("state") == "armed"
        if kind == "level":
            if ours or armed:  # the meter also runs while armed
                with self._lock:
                    self._position = int(event.get("position_frames", self._position))
                    now = time.monotonic()
                    while self._voice_levels and now - self._voice_levels[0][0] > 3:
                        self._voice_levels.popleft()
                    self._voice_levels.extend((now, float(v)) for v in
                                              event.get("peak_dbfs", [])
                                              if v is not None
                                              and math.isfinite(v) and v > -60)
                self.publish({"type": "record", "kind": "level",
                              "peak_dbfs": event.get("peak_dbfs", []),
                              "short_term_lufs": self._input_loudness.read(),
                              "clipped": event.get("clipped", []),
                              "position_frames": self._position})
            return
        if kind == "stopped":
            if self._ours(event) and event.get("take"):
                self._take_cart_end(event["take"])
                self._import_later(event["take"])
            self.publish({"type": "record", "kind": "status", "status": self.status()})
            return
        if kind in ("armed", "disarmed"):
            self.publish({"type": "record", "kind": "status", "status": self.status()})
            if kind == "disarmed":
                self._notice(event)
            return
        if kind == "started" or (ours and kind in ("device_lost", "device_back", "gap",
                                                   "worker_restarted")):
            self.publish({"type": "record", "kind": "status", "status": self.status()})
        if ours and kind != "started":
            self._notice(event)

    def _after_disconnect(self) -> None:
        """The recorder went away. If it was writing our take, it died with it: a fresh
        recorder repairs the files at its start, and the take is offered for import."""
        with self._lock:
            was_ours = self._ours(self._status) and self._recording(self._status)
            self._status = {"state": "idle"}
        self._set_available(False)
        if self._closed.is_set() or not was_ours:
            return
        notice = {"key": "record.event.recorder_lost", "level": "alarm", "params": {}}
        self._notices.append(notice)
        self.publish({"type": "record", "kind": "notice", **notice})
        with contextlib.suppress(OSError, RecorderError):
            self._spawn()
        self._wake.set()
