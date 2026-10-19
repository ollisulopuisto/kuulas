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
import os
import shutil
import threading
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from kuulas_recorder.client import RecorderClient, RecorderError, spawn_supervisor

from . import disk_budget, ops
from . import record_take as rt
from .messages import KuulasError, t

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
        self._available = False
        self._position = 0
        self._notices: deque = deque(maxlen=NOTICES_KEPT)
        #: Takes this editor imported (or found empty) -> what the import reported.
        self._imported: dict[str, dict | None] = {}
        self._we_armed = False  # this editor armed the recorder (pre-roll)
        self._closed = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        if watch:
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

    def recording_now(self) -> bool:
        """Is a take recording, as last heard (no question to the recorder: playback asks
        this on every play)? Any take counts: a speaker playing into a live microphone
        is what the owner's "no listening while recording" rule keeps out."""
        with self._lock:
            return self._recording(self._status)

    def _disk(self, status: dict) -> dict:
        """Recording time left: the recorder's estimate while a take runs, else ours."""
        left = (status.get("disk") or {}).get("seconds_left")
        if left is None:
            try:
                where = self.folder if self.folder.exists() else self.folder.parent
                free = shutil.disk_usage(where).free
                left = disk_budget.seconds_left(free, self.rate, 1, BYTES_PER_SAMPLE)
            except (OSError, ValueError):
                return {"seconds_left": None, "state": "ok", "text": ""}
        left = max(0, int(left))
        return {"seconds_left": left, "state": disk_budget.disk_state(left),
                "text": disk_budget.format_hm(left)}

    def status(self) -> dict:
        """Everything the record view shows, asked of the recorder afresh (never
        started for this: looking must not launch anything)."""
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
        return {
            "available": available,
            "state": status.get("state", "idle"),
            "recording": recording,
            # Listening into the pre-roll buffer, nothing written (the page says so).
            "armed": armed,
            "preroll_s": (status.get("armed") or {}).get("preroll_s") if armed else None,
            "preroll_frames": int(status.get("preroll_frames") or 0) if recording else 0,
            "ours": ours,
            "elsewhere": recording and not ours,
            "take": take,
            "position_frames": self._position if recording else 0,
            "rate": self.rate,
            "start_utc": status.get("start_utc") if recording else None,
            "device": status.get("device") if recording else None,
            "plan": None if plan is None else {"track_id": plan.track_id,
                                               "track_name": plan.track_name,
                                               "at": plan.at, "channel": plan.channel},
            "disk": self._disk(status if recording else {}),
            "gaps": len(status.get("gaps") or []) if isinstance(status.get("gaps"), list)
            else int(status.get("gaps") or 0),
            "notices": list(self._notices) if (recording and ours) else [],
            "pending": self.pending(running_take=take if ours else None),
            "hold_ms": self.hold_ms,
        }

    def arm(self, *, device: dict | None, channel: int, preroll_s: float) -> dict:
        """Listen for pre-roll (WP12c): the recorder opens the input and keeps the last
        ``preroll_s`` seconds in memory, writing nothing, so a take started next begins
        that long before Record was pressed. Arming again with the same settings only
        keeps it armed (the recorder lets go by itself when nobody does)."""
        if self.session.read_only:
            holder = self.session.package.locked_by or {}
            raise ops.EditError("error.history.read_only", host=holder.get("host", "?"))
        if not isinstance(channel, int) or channel < 1:
            raise RecordError("error.record.bad_channel", channel=channel)
        if (not isinstance(preroll_s, (int, float)) or isinstance(preroll_s, bool)
                or not 0 < preroll_s <= MAX_PREROLL_S):
            raise RecordError("error.record.bad_request", detail="preroll_s")
        args = {"channels": [channel], "rate": self.rate, "preroll_s": float(preroll_s)}
        if device:
            args["device"] = {"index": device.get("index"), "name": device.get("name")}
        answer = self._command("arm", spawn=True, **args)
        self._we_armed = True
        return self._publish_answer(answer)

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

    def start(self, *, device: dict | None, channel: int, track_id: str | None,
              name: str, at: int) -> dict:
        """Record a take into this project's ``recordings/``. ``track_id`` None (or
        ``"new"``): onto a new speech track named ``name``."""
        if self.session.read_only:
            holder = self.session.package.locked_by or {}
            raise ops.EditError("error.history.read_only", host=holder.get("host", "?"))
        if not isinstance(channel, int) or channel < 1:
            raise RecordError("error.record.bad_channel", channel=channel)
        if at < 0:
            raise RecordError("error.record.bad_request", detail="at")
        if track_id == "new":
            track_id = None
        if track_id is not None:
            track_name = ops._find_track(self.session.state, track_id).name
        else:
            track_name = (name or "").strip()
        self.folder.mkdir(parents=True, exist_ok=True)
        channel_label = rt.channel_name(track_name)
        for _attempt in range(3):  # another take may appear in between: next number
            take = rt.next_take(os.listdir(self.folder), channel_label, datetime.now(UTC))
            if not track_name:
                track_name = take
            plan = rt.TakePlan(take=take, at=int(at), track_id=track_id,
                               track_name=track_name, channel=channel,
                               device=dict(device or {}))
            # Before the recorder starts: a crash a moment later still knows the place.
            rt.write_plan(self.folder, plan)
            args = {"folder": str(self.folder), "take": take, "channels": [channel],
                    "names": [channel_label], "rate": self.rate}
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
            view = self._view(answer, True)
            self.publish({"type": "record", "kind": "status", "status": view})
            if answer.get("warning"):
                self._notice(answer["warning"] | {"event": "warning"})
            return view
        raise RecordError("error.record.take_exists", status=409, detail="")

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
        imported = self.import_take(take)
        self.publish({"type": "record", "kind": "status", "status": self.status()})
        return {"take": take, "imported": imported}

    # -- importing ----------------------------------------------------------------

    def _sidecar(self, take: str) -> dict | None:
        try:
            return json.loads((self.folder / f"{take}{rt.SIDECAR_SUFFIX}").read_text(
                encoding="utf-8"))
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
            clips = rt.clip_plan(sidecar, plan.at, on_disk)
            summary = rt.summary(sidecar)
            interrupted = sidecar.get("state") != "stopped"
            if not clips:
                self._imported[take] = None
                return None
            clip_name = t("record.take_interrupted", name=take) if interrupted else take
            _, clip_ids = self.session.import_take(
                [(self.folder / c.file, c.start, c.offset) for c in clips],
                track_id=plan.track_id, track_name=plan.track_name,
                clip_name=clip_name, take=take)
            result = {**summary, "take": take, "clips": len(clip_ids),
                      "clip_ids": clip_ids, "start": clips[0].start,
                      "interrupted": interrupted}
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
                self.publish({"type": "record", "kind": "level",
                              "peak_dbfs": event.get("peak_dbfs", []),
                              "clipped": event.get("clipped", []),
                              "position_frames": self._position})
            return
        if kind == "stopped":
            if self._ours(event) and event.get("take"):
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
