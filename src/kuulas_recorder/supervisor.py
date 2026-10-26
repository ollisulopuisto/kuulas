"""The supervisor: owns the socket and the take's journal, runs the worker.

It never touches audio (it does not import ``sounddevice``): a crash in the
audio driver or the capture code takes down the worker only. When the worker
dies the supervisor repairs its files, journals the gap, tells the clients and
starts a new worker into the next numbered file set. When the device is lost
it waits for it to come back (asking a fresh process for the device list each
second) and continues the take in a new segment.

Clients (the editor) only watch and send commands. Quitting or crashing a
client never stops a recording, and a client that connects later gets the
running state from ``hello`` / ``status``. A client that stops reading is
disconnected after a few seconds; it can never block the supervisor.

Every protocol message is described in docs/RECORDER.md.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import math
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from kuulas_recorder import PROTOCOL, version
from kuulas_recorder import names as naming
from kuulas_recorder.journal import TakeRecord, atomic_write_json, utc_iso
from kuulas_recorder.power import KeepAwake
from kuulas_recorder.sources import SourceError, check_rate, resolve_device
from kuulas_recorder.transport import Connection, Listener, UnixTransport
from kuulas_recorder.wavfile import BYTES_PER_FRAME

log = logging.getLogger("kuulas_recorder")

# Worker exit codes (worker.py).
EXIT_OK, EXIT_DEVICE_LOST, EXIT_DISK_FULL = 0, 2, 3

# Disk thresholds, in seconds of recording left at the take's data rate.
WARN_SECONDS = (1800, 600, 120)  # 30 min (the plan's "loud warning"), 10, 2 min
START_MIN_SECONDS = 60  # refuse to start a take with less room than this
STOP_SECONDS = 10  # stop gracefully, everything flushed, at this much room left
# Space never counted as usable: macOS itself misbehaves on a full disk.
RESERVE_BYTES = 200 * 1024 * 1024

# A worker that dies this many times in a row without a successful flush is
# not restarted again: the take stops with an error instead of a crash loop.
RESTART_LIMIT = 5

# Pre-roll (WP12c). An armed recorder listens with the microphone open, so it
# disarms itself unless a client keeps arming it (the editor does every 20 s):
# an editor that crashed or was closed must not leave the microphone listening.
ARM_TTL_S = 120.0
# Idle (no take, not listening) with no client connected for this long: the recorder
# exits by itself instead of running for ever. An open editor keeps a connection, so
# this only ends a recorder nobody uses any more.
IDLE_EXIT_S = 60.0
MAX_PREROLL_S = 600.0  # a ten-minute buffer is ~85 MB per channel as float32
ARMED_STATES = ("arming", "armed", "disarming")

LEVEL_FLOOR_DB = -120.0
CLIENT_QUEUE = 512  # events queued for one client before it counts as stuck
CLIENT_SEND_TIMEOUT = 5.0


class ProtocolError(Exception):
    """An error answer: a stable machine ``key`` and a plain English ``text``."""

    def __init__(self, key: str, text: str):
        super().__init__(text)
        self.key = key
        self.text = text


def disk_free(path: Path) -> int:
    return shutil.disk_usage(path).free


def list_devices_subprocess(timeout: float = 15.0) -> list[dict]:
    """The input devices, from a fresh process: PortAudio only sees devices that
    were there when it started, and the supervisor must not load it at all."""
    proc = subprocess.run(
        [sys.executable, "-m", "kuulas_recorder", "devices", "--json"],
        capture_output=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise ProtocolError("device_list_failed",
                            "Could not list the input devices: "
                            + proc.stderr.decode(errors="replace").strip()[-300:])
    return json.loads(proc.stdout)


def to_dbfs(peak: float) -> float:
    if peak <= 0:
        return LEVEL_FLOOR_DB
    return max(LEVEL_FLOOR_DB, round(20 * math.log10(peak), 1))


class Client:
    """One connected client: a reader thread and a sender thread with a bounded
    queue. If the queue fills (the client stopped reading) it is disconnected."""

    def __init__(self, sup: Supervisor, conn: Connection, n: int):
        self.sup = sup
        self.conn = conn
        self.n = n
        self.events = False
        self.levels = False
        self.peaks: list[float] = []
        self.closed = False
        self.after_reply: Callable[[], None] | None = None
        self._q: queue.Queue = queue.Queue(CLIENT_QUEUE)
        threading.Thread(target=self._read, name=f"client-{n}-in", daemon=True).start()
        threading.Thread(target=self._send, name=f"client-{n}-out", daemon=True).start()

    def push(self, msg: dict, *, after_send: Callable[[], None] | None = None) -> None:
        if self.closed:
            if after_send is not None:
                after_send()
            return
        try:
            self._q.put_nowait((msg, after_send))
        except queue.Full:
            log.warning("client %d is not reading; disconnecting it", self.n)
            self.close()
            if after_send is not None:
                after_send()

    def _send(self) -> None:
        while not self.closed:
            item = self._q.get()
            if item is None:
                break
            msg, after_send = item
            try:
                self.conn.send(json.dumps(msg).encode() + b"\n",
                               timeout=CLIENT_SEND_TIMEOUT)
            except OSError:
                log.info("client %d gone (send failed)", self.n)
                break
            finally:
                # Quit must be acknowledged before the main thread closes sockets.
                # If delivery fails, the requested idle shutdown still goes ahead.
                if after_send is not None:
                    after_send()
        self.close()

    def _read(self) -> None:
        while True:
            line = self.conn.read_line()
            if line is None:
                break
            if not line.strip():
                continue
            reply = self.sup.handle_line(self, line)
            after_send, self.after_reply = self.after_reply, None
            self.push(reply, after_send=after_send)
        self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        with contextlib.suppress(queue.Full):
            self._q.put_nowait(None)
        self.conn.close()
        self.sup.forget(self)


class Worker:
    """One worker process and the threads that read its events and its exit."""

    def __init__(self, sup: Supervisor, gen: int, argv: list[str], config: dict,
                 stderr):
        self.gen = gen
        self.segment = config["segment"]
        self.proc = subprocess.Popen(  # noqa: S603 - our own module, fixed argv
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
            close_fds=True)
        self.last_heard = time.monotonic()
        self.error: tuple[str, str] | None = None
        self.lost_reason: str | None = None
        self.segments: list[int] = []
        self.first_block = False
        self.flushed = False
        self.send(json.dumps(config))
        self._reader = threading.Thread(target=self._read, args=(sup,),
                                        name=f"worker-{gen}-out", daemon=True)
        self._reader.start()
        threading.Thread(target=self._wait, args=(sup,), name=f"worker-{gen}-wait",
                         daemon=True).start()

    @property
    def pid(self) -> int:
        return self.proc.pid

    def send(self, line: str) -> None:
        with contextlib.suppress(OSError, ValueError):
            self.proc.stdin.write(line.encode() + b"\n")  # type: ignore[union-attr]
            self.proc.stdin.flush()  # type: ignore[union-attr]

    def kill(self) -> None:
        with contextlib.suppress(OSError):
            self.proc.kill()

    def _read(self, sup: Supervisor) -> None:
        for raw in self.proc.stdout:  # type: ignore[union-attr]
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            self.last_heard = time.monotonic()
            sup.on_worker_event(self, ev)

    def _wait(self, sup: Supervisor) -> None:
        code = self.proc.wait()
        # Let the reader deliver the last events (the final frame counts) first.
        self._reader.join(timeout=5)
        sup.on_worker_exit(self, code)


class Supervisor:
    def __init__(self, socket_path: Path | str, state_dir: Path | str | None = None, *,
                 transport=None, worker_argv: list[str] | None = None,
                 list_devices: Callable[[], list[dict]] = list_devices_subprocess,
                 disk_free: Callable[[Path], int] = disk_free,
                 keep_awake=None, flush_seconds: float = 1.0, blocksize: int = 1024,
                 max_data_bytes: int | None = None, start_timeout: float = 10.0,
                 stop_timeout: float = 15.0, tick: float = 0.25,
                 device_poll: float = 1.0, stuck_after: float | None = None,
                 restart_backoff: float = 0.2, arm_ttl: float = ARM_TTL_S,
                 idle_exit: float | None = IDLE_EXIT_S):
        self.socket_path = Path(socket_path)
        self.state_dir = Path(state_dir) if state_dir else self.socket_path.parent
        self.transport = transport or UnixTransport()
        self.worker_argv = worker_argv or [sys.executable, "-m", "kuulas_recorder",
                                           "worker"]
        self.list_devices = list_devices
        self.disk_free = disk_free
        self.keep_awake = keep_awake or KeepAwake()
        self.flush_seconds = flush_seconds
        self.blocksize = blocksize
        self.max_data_bytes = max_data_bytes
        self.start_timeout = start_timeout
        self.stop_timeout = stop_timeout
        self.tick = tick
        self.device_poll = device_poll
        self.restart_backoff = restart_backoff
        self.arm_ttl = arm_ttl
        self.idle_exit = idle_exit
        self._idle_since: float | None = None
        self.armed: dict | None = None  # what the armed worker listens to
        self.armed_device: dict | None = None  # the device's full description
        self.armed_until = 0.0
        self.disarm_reason: str | None = None
        # Longer than the worker's ring (20 s): a disk that stalls and recovers
        # inside that time loses nothing, and killing the worker would.
        self.stuck_after = stuck_after or max(30.0, 5 * flush_seconds)

        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.state = "idle"
        self.take: TakeRecord | None = None
        self.params: dict = {}
        self.worker: Worker | None = None
        self.gen = 0
        self.failures = 0  # worker deaths in a row without a flush
        self.restart_at = 0.0
        self.gap_reason = ""
        self.stop_reason: str | None = None
        self.stop_deadline = 0.0
        self.start_error: tuple[str, str] | None = None
        self.last_take: dict | None = None
        self.recovered: list[dict] = []
        self.overflow_base = 0  # overflows counted by earlier workers of this take
        self.overflow_journaled_at = 0.0
        self.warned: set[int] = set()
        self.next_device_poll = 0.0
        self.disk_seconds: float | None = None
        self.disk_free_bytes: int | None = None
        self.clients: set[Client] = set()
        self.client_n = 0
        self.listener: Listener | None = None
        self.shutdown_requested = threading.Event()
        self.closed = threading.Event()
        self._lock_fd: int | None = None
        self._stderr = None
        # close() runs from whoever gets there first (the main thread after a signal, a
        # client's thread right after a quit reply); a second caller waits for the first.
        self._close_lock = threading.RLock()

    # --- life cycle -------------------------------------------------------------

    def open(self) -> None:
        """Take the single-instance lock, recover a take left by a crash, listen."""
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.state_dir / "recorder.lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            raise ProtocolError("already_running",
                                "Another kuulas-recorder is already running.") from e
        self._lock_fd = fd
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        self._stderr = open(self.state_dir / "worker.log", "ab")  # noqa: SIM115 - kept open
        self.recover_after_crash()
        self.listener = self.transport.listen(self.socket_path)
        threading.Thread(target=self._accept, name="accept", daemon=True).start()
        threading.Thread(target=self._monitor, name="monitor", daemon=True).start()
        log.info("listening on %s (pid %d)", self.socket_path, os.getpid())

    def recover_after_crash(self) -> None:
        """A take left ``recording`` by a killed recorder is repaired at start."""
        _recover(self)

    def serve_forever(self) -> None:
        self.open()
        self.wait_for_shutdown()

    def wait_for_shutdown(self) -> None:
        self.shutdown_requested.wait()
        self.close()

    def request_shutdown(self) -> None:
        """SIGTERM / SIGINT: stop the take cleanly (everything flushed), then exit."""
        self.shutdown_requested.set()

    def close(self) -> None:
        with self._close_lock:
            if self.closed.is_set():
                return
            self._close()

    def _close(self) -> None:
        with self.lock:
            state = self.state
        if state in ARMED_STATES:
            self.disarm("shutdown")
        elif state != "idle":
            with contextlib.suppress(ProtocolError):
                self.stop("shutdown", wait=True)
        if self.listener is not None:
            self.listener.close()
        for c in list(self.clients):
            c.close()
        self.keep_awake.stop()
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
        if self._stderr is not None:
            self._stderr.close()
        self.closed.set()
        log.info("closed")

    def _accept(self) -> None:
        while not self.closed.is_set():
            conn = self.listener.accept() if self.listener else None
            if conn is None:
                return
            with self.lock:
                self.client_n += 1
                c = Client(self, conn, self.client_n)
                self.clients.add(c)

    def forget(self, client: Client) -> None:
        with self.lock:
            self.clients.discard(client)

    # --- events to clients ------------------------------------------------------

    def emit(self, event: str, **fields) -> None:
        msg = {"event": event, **fields}
        with self.lock:
            targets = [c for c in self.clients if c.events]
        for c in targets:
            c.push(msg)

    def warn(self, key: str, text: str, **fields) -> None:
        log.warning("%s: %s", key, text)
        self.emit("warning", key=key, text=text, **fields)

    # --- protocol ---------------------------------------------------------------

    def handle_line(self, client: Client, line: bytes) -> dict:
        bad = {"ok": False, "error": {"key": "bad_request",
                                      "text": "A command is one JSON object a line."}}
        try:
            msg = json.loads(line)
        except ValueError:
            return bad
        if not isinstance(msg, dict):
            return bad
        rid = msg.get("id")
        cmd = msg.get("cmd")
        fn = getattr(self, f"cmd_{cmd}", None) if isinstance(cmd, str) else None
        if fn is None:
            return {"id": rid, "ok": False, "error": {
                "key": "unknown_command", "text": f"Unknown command {cmd!r}."}}
        try:
            result = fn(client, msg)
        except ProtocolError as e:
            return {"id": rid, "ok": False, "error": {"key": e.key, "text": e.text}}
        except Exception as e:
            log.exception("command %r failed", cmd)
            return {"id": rid, "ok": False,
                    "error": {"key": "internal", "text": f"Internal error: {e!r}"}}
        return {"id": rid, "ok": True, **result}

    def cmd_hello(self, client: Client, msg: dict) -> dict:
        if msg.get("subscribe"):
            self.cmd_subscribe(client, msg)
        return {"protocol": PROTOCOL, "version": version(), "pid": os.getpid(),
                "status": self.status()}

    def cmd_ping(self, _client: Client, _msg: dict) -> dict:
        return {"pong": True, "utc": utc_iso()}

    def cmd_subscribe(self, client: Client, msg: dict) -> dict:
        client.events = bool(msg.get("events", True))
        client.levels = bool(msg.get("levels", False))
        return {"events": client.events, "levels": client.levels}

    def cmd_devices(self, _client: Client, _msg: dict) -> dict:
        return {"devices": self._devices()}

    def cmd_status(self, _client: Client, _msg: dict) -> dict:
        return self.status()

    def cmd_levels(self, client: Client, _msg: dict) -> dict:
        with self.lock:
            names = self.take.names if self.take else []
            peaks = client.peaks or [0.0] * len(names)
            client.peaks = [0.0] * len(names)
        return {"names": names, "peak_dbfs": [to_dbfs(p) for p in peaks],
                "clipped": [p >= 1.0 for p in peaks]}

    def cmd_mark(self, _client: Client, msg: dict) -> dict:
        text = msg.get("text", "")
        if not isinstance(text, str) or len(text) > 1000:
            raise ProtocolError("bad_request", "A marker's text is a string of at most "
                                "1000 characters.")
        with self.lock:
            take = self.take
            if take is None or take.data["start_monotonic_ns"] is None:
                raise ProtocolError("not_recording", "No take is recording.")
            at = self.position()
            mark = {"at_frame": at, "text": text, "utc": utc_iso()}
            take.data["markers"].append(mark)
            take.journal("mark", at_frame=at, text=text)
            take.save()
        self.emit("marked", take=take.take, **mark)
        return mark

    def cmd_start(self, _client: Client, msg: dict) -> dict:
        return self.start(msg)

    def cmd_stop(self, _client: Client, _msg: dict) -> dict:
        return self.stop("stopped", wait=True)

    def cmd_arm(self, _client: Client, msg: dict) -> dict:
        return self.arm(msg)

    def cmd_disarm(self, _client: Client, _msg: dict) -> dict:
        self.disarm("disarmed")
        return self.status()

    def cmd_repair(self, _client: Client, msg: dict) -> dict:
        folder, take = msg.get("folder"), msg.get("take")
        if not isinstance(folder, str) or not naming.valid_name(take):
            raise ProtocolError("bad_request", "repair needs a folder and a take name.")
        with self.lock:
            if self.take is not None and self.take.folder == Path(folder) and (
                    self.take.take == take):
                raise ProtocolError("busy", "That take is recording now.")
        return recover_take(Path(folder), take)

    def cmd_quit(self, client: Client, _msg: dict) -> dict:
        with self.lock:
            if self.state not in ("idle", *ARMED_STATES):
                raise ProtocolError("busy", "A take is recording; stop it first.")
        client.after_reply = self.request_shutdown
        return {"quitting": True}

    def _devices(self) -> list[dict]:
        try:
            return self.list_devices()
        except ProtocolError:
            raise
        except Exception as e:
            raise ProtocolError("device_list_failed",
                                f"Could not list the input devices: {e}") from e

    # --- state ------------------------------------------------------------------

    def position(self) -> int:
        """The take's current frame on its recording clock (``now``)."""
        take = self.take
        if take is None or take.data["start_monotonic_ns"] is None:
            return 0
        dt = time.monotonic_ns() - int(take.data["start_monotonic_ns"])
        return max(0, dt * take.rate // 1_000_000_000)

    def status(self) -> dict:
        with self.lock:
            take = self.take
            out: dict = {"state": self.state, "pid": os.getpid(),
                         "worker_pid": self.worker.pid if self.worker else None,
                         "last_take": self.last_take, "recovered": self.recovered}
            if self.armed is not None and self.state in ARMED_STATES:
                out["armed"] = dict(self.armed)
            if take is not None:
                d = take.data
                out.update({
                    "take": take.take, "folder": str(take.folder),
                    "device": d["device"], "channels": d["channels"], "rate": d["rate"],
                    "start_utc": d["start_utc"], "position_frames": self.position(),
                    "preroll_frames": d.get("preroll_frames", 0),
                    "frames_flushed": take.last_end(), "segments": d["segments"],
                    "gaps": d["gaps"], "dropouts": len(d["dropouts"]),
                    "failed_channels": d.get("failed_channels", []),
                    "overflows": d["overflows"], "worker_restarts": d["worker_restarts"],
                    "markers": len(d["markers"]),
                    "disk": {"free_bytes": self.disk_free_bytes,
                             "seconds_left": self.disk_seconds},
                })
            return out

    def bytes_per_second(self) -> int:
        take = self.take
        if take is None:
            return 0
        return take.rate * BYTES_PER_FRAME * len(take.names)

    def disk_check(self, folder: Path, bps: int) -> tuple[int, float]:
        free = int(self.disk_free(folder))
        return free, max(0.0, (free - RESERVE_BYTES) / bps)

    # --- start ------------------------------------------------------------------

    def start(self, msg: dict) -> dict:
        folder, take = msg.get("folder"), msg.get("take")
        channels = msg.get("channels", [1])
        names = msg.get("names")
        rate = msg.get("rate", 48000)
        if not isinstance(folder, str) or not os.path.isabs(folder):
            raise ProtocolError("bad_request", "start needs an absolute folder path.")
        if not naming.valid_name(take):
            raise ProtocolError("bad_name", f"{take!r} is not a usable take name.")
        if (not isinstance(channels, list) or not channels
                or not all(isinstance(c, int) and not isinstance(c, bool) and c >= 1
                           for c in channels) or len(set(channels)) != len(channels)):
            raise ProtocolError("bad_request",
                                "channels is a list of distinct device channel "
                                "numbers, counted from 1.")
        if names is None:
            names = [f"ch{c}" for c in channels]
        if (not isinstance(names, list) or len(names) != len(channels)
                or len(set(names)) != len(names)
                or not all(naming.valid_name(n) for n in names)):
            raise ProtocolError("bad_name", "names needs one distinct, usable name per "
                                "channel (letters, digits, spaces, - _ . , ( ) ' + &).")
        if (not isinstance(rate, int) or isinstance(rate, bool)
                or not 8000 <= rate <= 384000):
            raise ProtocolError("bad_request", "rate is a sample rate in Hz.")
        path = Path(folder)
        with self.lock:
            before = self.state
            if before in ("arming", "disarming"):
                raise ProtocolError("busy", "The recorder is changing between "
                                    "listening and idle; try again.")
            if before not in ("idle", "armed"):
                raise ProtocolError("already_recording", "A take is already recording.")
            listening = before == "armed"  # a worker is listening: it holds the pre-roll
            if listening:
                self._check_armed_start(channels, rate, msg)
            self.state = "checking"
        try:
            if listening:
                self._check_take(path, take, names, rate)
                device = self.armed_device
            else:
                device = self._check_start(path, take, channels, names, rate, msg)
        except BaseException:
            with self.lock:
                self.state = before  # still listening, if it was
            raise
        with self.lock:
            if listening and self.worker is None:  # the listener died in between
                self.state = "idle"
                raise ProtocolError("worker_failed", "The listening recorder stopped; "
                                    "press Record again.")
            self.take = TakeRecord.new(path, take, rate=rate, device=device,
                                       channels=channels, names=names)
            self.params = {"device": {"index": device["index"], "name": device["name"]},
                           "channels": channels, "names": names, "rate": rate,
                           "folder": str(path), "take": take}
            self.state = "starting"
            self.failures = 0
            self.overflow_base = 0
            self.warned = set()
            self.stop_reason = None
            self.start_error = None
            atomic_write_json(self.state_dir / "current.json", self.params)
            self.keep_awake.start()
            if listening:
                self.armed = None
                self.worker.send(json.dumps({"cmd": "record", "folder": str(path),
                                             "take": take, "names": names}))
            else:
                self._spawn(1)
            deadline = time.monotonic() + self.start_timeout
            while self.state == "starting":
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self.changed.wait(left)
            if self.state == "starting":
                self.start_error = ("device_no_audio",
                                    f"{device['name']} opened but sent no audio.")
                if self.worker is not None:
                    self.worker.kill()
                while self.state == "starting":
                    self.changed.wait(1.0)
            if self.start_error is not None and self.state == "idle":
                key, text = self.start_error
                raise ProtocolError(key, text)
            status = self.status()
        warn = self._disk_warning_now()
        if warn:
            status["warning"] = warn
        return status

    def _check_start(self, path: Path, take: str, channels: list[int],
                     names: list[str], rate: int, msg: dict) -> dict:
        self._check_take(path, take, names, rate)
        return self._check_device(channels, rate, msg.get("device"))

    def _check_armed_start(self, channels: list[int], rate: int, msg: dict) -> None:
        """A take started while listening must be what is being listened to: the
        buffered audio is of that device and those channels (lock held)."""
        a = self.armed
        want = msg.get("device")
        named = want.get("name") if isinstance(want, dict) else want
        if (a is None or channels != a["channels"] or rate != a["rate"]
                or (isinstance(named, str) and named != a["device"]["name"])):
            raise ProtocolError("armed_mismatch", "The recorder is listening to other "
                                "channels or another input than this take asks for; "
                                "arm it again first.")

    def _check_take(self, path: Path, take: str, names: list[str], rate: int) -> None:
        if (path / naming.sidecar_file(take)).exists() or any(
                (path / naming.segment_file(take, n, 1)).exists() for n in names):
            raise ProtocolError("take_exists",
                                f"Take {take} already exists in {path}; a take is "
                                "never overwritten.")
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ProtocolError("folder_not_writable",
                                f"Cannot create {path}: {e.strerror or e}") from e
        if not os.access(path, os.W_OK):
            raise ProtocolError("folder_not_writable", f"Cannot write to {path}.")
        bps = rate * BYTES_PER_FRAME * len(names)
        free, seconds = self.disk_check(path, bps)
        self.disk_free_bytes, self.disk_seconds = free, seconds
        if seconds < START_MIN_SECONDS:
            raise ProtocolError("disk_full",
                                f"Only {free // (1024 * 1024)} MB free on the disk of "
                                f"{path}: not enough to record.")

    def _check_device(self, channels: list[int], rate: int, want: object) -> dict:
        try:
            device = resolve_device(self._devices(), want)
            check_rate(device["name"], device["default_rate"], rate)
        except SourceError as e:
            raise ProtocolError(e.key, e.text) from e
        if device["channels"] < max(channels):
            raise ProtocolError("channels_unavailable",
                                f"{device['name']} has {device['channels']} input "
                                f"channels; channel {max(channels)} was asked for.")
        return device

    # --- arm: listen into the pre-roll buffer (WP12c) --------------------------------

    def arm(self, msg: dict) -> dict:
        """Open the input and keep the last ``preroll_s`` seconds in memory, writing
        nothing. A ``start`` for the same input and channels then begins the take that
        many seconds before it. Arming again with the same settings only extends the
        time-to-live (``arm_ttl``); other settings replace the listener."""
        channels = msg.get("channels", [1])
        rate = msg.get("rate", 48000)
        preroll = msg.get("preroll_s")
        if (not isinstance(preroll, (int, float)) or isinstance(preroll, bool)
                or not 0 < preroll <= MAX_PREROLL_S):
            raise ProtocolError("bad_request", f"preroll_s is seconds, above 0 and at "
                                f"most {MAX_PREROLL_S:g}.")
        if (not isinstance(channels, list) or not channels
                or not all(isinstance(c, int) and not isinstance(c, bool) and c >= 1
                           for c in channels) or len(set(channels)) != len(channels)):
            raise ProtocolError("bad_request", "channels is a list of distinct device "
                                "channel numbers, counted from 1.")
        if (not isinstance(rate, int) or isinstance(rate, bool)
                or not 8000 <= rate <= 384000):
            raise ProtocolError("bad_request", "rate is a sample rate in Hz.")
        device = self._check_device(channels, rate, msg.get("device"))
        wanted = {"device": {"index": device["index"], "name": device["name"]},
                  "channels": channels, "rate": rate, "preroll_s": float(preroll)}
        with self.lock:
            if self.state == "armed" and self.armed == wanted and self.worker is not None:
                self.armed_until = time.monotonic() + self.arm_ttl
                return self.status()
        if self.state in ARMED_STATES:
            self.disarm("rearmed")
        with self.lock:
            if self.state != "idle":
                raise ProtocolError("already_recording", "A take is already recording.")
            self.state = "arming"
            self.armed, self.armed_device = wanted, device
            self.disarm_reason = None
            self.start_error = None
            config = dict(wanted, armed=True, preroll_seconds=wanted["preroll_s"],
                          segment=1, flush_seconds=self.flush_seconds,
                          blocksize=self.blocksize)
            self.gen += 1
            try:
                self.worker = Worker(self, self.gen, self.worker_argv, config,
                                     self._stderr)
            except OSError as e:
                self._end_arming()
                raise ProtocolError("worker_failed",
                                    f"Could not start the recorder: {e}") from e
            deadline = time.monotonic() + self.start_timeout
            while self.state == "arming":
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self.changed.wait(left)
            if self.state == "arming":
                self.start_error = ("device_no_audio",
                                    f"{device['name']} opened but sent no audio.")
                if self.worker is not None:
                    self.worker.kill()
                while self.state == "arming":
                    self.changed.wait(1.0)
            if self.state != "armed":
                key, text = self.start_error or ("worker_failed", "The recorder stopped.")
                raise ProtocolError(key, text)
            self.armed_until = time.monotonic() + self.arm_ttl
            return self.status()

    def _end_arming(self) -> None:
        self.armed = self.armed_device = None
        self.worker = None
        self.state = "idle"
        self.changed.notify_all()

    def disarm(self, reason: str) -> None:
        """Stop listening and drop the buffer. Nothing was written, so nothing remains.
        Harmless when not armed."""
        with self.lock:
            if self.state not in ARMED_STATES:
                return
            self.disarm_reason = reason
            self.state = "disarming"
            if self.worker is not None:
                self.worker.send("stop")
            deadline = time.monotonic() + self.stop_timeout
            while self.state == "disarming":
                left = deadline - time.monotonic()
                if left <= 0:
                    if self.worker is not None:
                        self.worker.kill()
                    self.changed.wait(1.0)
                    continue
                self.changed.wait(left)

    def _on_armed_exit(self, w: Worker, code: int) -> None:
        """The listening worker is gone (lock held)."""
        was = self.state
        reason = self.disarm_reason
        if reason is None:
            reason = "device_lost" if (code == EXIT_DEVICE_LOST or w.lost_reason) else (
                "worker_died")
        if was == "arming" and self.start_error is None:
            if w.lost_reason:
                self.start_error = ("device_no_audio", "The input opened but sent "
                                    "no audio.")
            else:
                self.start_error = w.error or (
                    "worker_failed", f"The recorder stopped at start (exit {code}).")
        self.armed = self.armed_device = None
        self.state = "idle"
        if was != "arming":
            log.info("disarmed (%s)", reason)
            self.emit("disarmed", reason=reason,
                      text="The recorder stopped listening; nothing was recorded."
                      if reason not in ("device_lost", "worker_died") else
                      "The input stopped, so the recorder stopped listening. "
                      "Nothing was recorded.")
        self.changed.notify_all()

    def _disk_warning_now(self) -> dict | None:
        s = self.disk_seconds
        if s is not None and s < WARN_SECONDS[0]:
            return {"key": "disk_low", "seconds_left": round(s),
                    "text": f"About {round(s / 60)} minutes of recording space left."}
        return None

    def _spawn(self, segment: int) -> None:
        """Start a worker for segment ``segment`` (lock held)."""
        self.gen += 1
        config = dict(self.params, segment=segment, flush_seconds=self.flush_seconds,
                      blocksize=self.blocksize)
        if self.max_data_bytes:
            config["max_data_bytes"] = self.max_data_bytes
        try:
            self.worker = Worker(self, self.gen, self.worker_argv, config, self._stderr)
        except OSError as e:
            log.exception("could not start a worker")
            self.worker = None
            self.failures += 1
            self.start_error = ("worker_failed", f"Could not start the recorder: {e}")
            self.restart_at = time.monotonic() + 1.0
            if self.state == "starting":
                self._end_failed_start()
            return
        log.info("worker %d started (pid %d) for segment %d", self.gen, self.worker.pid,
                 segment)

    # --- worker events ----------------------------------------------------------

    def on_worker_event(self, w: Worker, ev: dict) -> None:
        kind = ev.get("ev")
        with self.lock:
            if w is not self.worker:
                return
            if self.state in ARMED_STATES:
                self._on_armed_event(w, ev)
                return
            take = self.take
            if take is None:
                return
            if kind == "preroll":
                take.data["preroll_frames"] = int(ev.get("frames", 0))
                return
            if kind == "opened":
                self._on_opened(w, ev)
            elif kind == "first_block":
                self._on_first_block(w, ev)
            elif kind in ("flushed", "closed"):
                self._on_frames(w, ev)
            elif kind == "levels":
                self._on_levels(ev)
                return  # no snapshot write for meters
            elif kind == "overflow":
                self._on_overflow(ev)
            elif kind == "dropout":
                at = self._abs_frame(ev)
                take.data["dropouts"].append({"at_frame": at, "frames": ev["frames"]})
                take.journal("dropout", at_frame=at, frames=ev["frames"])
                self.warn("dropout", "The disk fell behind; a stretch of silence was "
                          "written to keep the take in time.", at_frame=at,
                          frames=ev["frames"])
            elif kind == "channel_failed":
                self._on_channel_failed(ev)
            elif kind == "device_lost":
                w.lost_reason = ev.get("reason") or "lost"
            elif kind == "error":
                w.error = (ev.get("key", "worker_failed"), ev.get("text", ""))
                log.warning("worker error %s: %s", *w.error)
            elif kind in ("hello", "started", "stopped"):
                return
            self.changed.notify_all()

    def _on_channel_failed(self, ev: dict) -> None:
        """One channel's file failed (lock held, WP12b): the take goes on with the other
        channels; the sidecar and journal say which channel stopped, and where."""
        take = self.take
        at = self._abs_frame(ev)
        name = str(ev.get("name", ""))
        take.data.setdefault("failed_channels", []).append(
            {"name": name, "at_frame": at, "text": str(ev.get("text", ""))})
        take.journal("channel_failed", name=name, at_frame=at, text=ev.get("text", ""))
        take.save()
        self.warn("channel_failed",
                  f"Channel {name} stopped recording; the others go on.",
                  name=name, at_frame=at)

    def _on_armed_event(self, w: Worker, ev: dict) -> None:
        """What a listening worker says (lock held): it hears audio, meters, trouble."""
        kind = ev.get("ev")
        if kind == "listening" and self.state == "arming":
            self.state = "armed"
            self.armed_until = time.monotonic() + self.arm_ttl
            self.emit("armed", **self.armed)
        elif kind == "levels":
            self._on_levels(ev)
            return
        elif kind == "device_lost":
            w.lost_reason = ev.get("reason") or "lost"
        elif kind == "error":
            w.error = (ev.get("key", "worker_failed"), ev.get("text", ""))
            log.warning("worker error %s: %s", *w.error)
        self.changed.notify_all()

    def _abs_frame(self, ev: dict) -> int:
        """A frame counted within a worker (``at``) on the take's clock."""
        take = self.take
        first = take.segment(self.worker.segments[0]) if self.worker.segments else None
        base = first["start_frame"] if first and first["start_frame"] is not None else 0
        return base + int(ev.get("at", 0))

    def _on_opened(self, w: Worker, ev: dict) -> None:
        take = self.take
        n = int(ev["segment"])
        seg = take.add_segment(n, ev["files"])
        w.segments.append(n)
        if ev.get("continues"):
            take.place_segment(seg, take.last_end(before=n))
            take.journal("segment", segment=n, start_frame=seg["start_frame"],
                         reason="size_limit")
            take.save()

    def _on_first_block(self, w: Worker, ev: dict) -> None:
        take = self.take
        seg = take.segment(int(ev["segment"]))
        if seg is None or seg["start_frame"] is not None:
            return
        w.first_block = True
        d = take.data
        if d["start_monotonic_ns"] is None:
            d["start_monotonic_ns"] = int(ev["mono_ns"])
            d["start_utc"] = utc_iso(int(ev["utc_ns"]))
            take.place_segment(seg, 0)
            take.save()
            take.journal("started", start_utc=d["start_utc"], device=d["device"],
                         channels=d["channels"], rate=d["rate"])
            self.state = "recording"
            self.emit("started", take=take.take, folder=str(take.folder),
                      start_utc=d["start_utc"], device=d["device"],
                      channels=d["channels"])
            return
        prev_end = take.last_end(before=seg["segment"])
        at = (int(ev["mono_ns"]) - int(d["start_monotonic_ns"])) * take.rate
        start = max(prev_end, at // 1_000_000_000)
        take.place_segment(seg, start)
        gap = start - prev_end
        reason = self.gap_reason or "restart"
        if gap > 0:
            d["gaps"].append({"at_frame": prev_end, "frames": gap, "reason": reason})
        take.journal("gap", at_frame=prev_end, frames=gap, reason=reason,
                     segment=seg["segment"])
        take.save()
        self.state = "recording"
        self.emit("gap", take=take.take, at_frame=prev_end, frames=gap, reason=reason,
                  segment=seg["segment"])

    def _on_frames(self, w: Worker, ev: dict) -> None:
        take = self.take
        seg = take.segment(int(ev["segment"]))
        if seg is None:
            return
        for name, frames in ev.get("frames", {}).items():
            if name in seg["files"]:
                seg["files"][name]["frames"] = int(frames)
        if ev["ev"] == "flushed":
            w.flushed = True
            self.failures = 0
            if "overflows" in ev:
                take.data["overflows"] = self.overflow_base + int(ev["overflows"])
        else:
            seg["end"] = seg["end"] or "closed"
        if take.started:  # no sidecar for a take that never got audio
            take.save()
        if ev["ev"] == "flushed":
            self._disk_tick()

    def _on_levels(self, ev: dict) -> None:
        peaks = [float(p) for p in ev.get("peaks", [])]
        targets = []
        for c in self.clients:
            if len(c.peaks) != len(peaks):
                c.peaks = [0.0] * len(peaks)
            c.peaks = [max(a, b) for a, b in zip(c.peaks, peaks, strict=True)]
            if c.levels:
                targets.append(c)
        msg = {"event": "level", "peak_dbfs": [to_dbfs(p) for p in peaks],
               "clipped": [p >= 1.0 for p in peaks], "position_frames": self.position()}
        for c in targets:
            c.push(msg)

    def _on_overflow(self, ev: dict) -> None:
        take = self.take
        d = take.data
        at = self._abs_frame(ev)
        d["overflows"] = self.overflow_base + int(ev.get("count", 1))
        if len(d["overflow_at"]) < 1000:
            d["overflow_at"].append(at)
        now = time.monotonic()
        if now - self.overflow_journaled_at >= 1.0:
            # Overflows come in bursts of one per block; journal and warn once a second.
            self.overflow_journaled_at = now
            take.journal("overflow", at_frame=at, count=d["overflows"])
            self.warn("input_overflow", "The input overflowed: some audio was lost "
                      "before it reached the recorder.", at_frame=at,
                      count=d["overflows"])

    # --- worker exit ------------------------------------------------------------

    def on_worker_exit(self, w: Worker, code: int) -> None:
        with self.lock:
            if w is not self.worker:
                return
            self.worker = None
            log.info("worker %d exited with %s", w.gen, code)
            if self.state in ARMED_STATES:
                self._on_armed_exit(w, code)
                return
            take = self.take
            if take is not None:
                for n in w.segments:
                    seg = take.segment(n)
                    if seg is not None:
                        take.repair_segment(seg)
                self.overflow_base = take.data["overflows"]
            if self.state == "starting" and not w.first_block:
                if self.start_error is None and w.error is None and w.lost_reason:
                    name = take.data["device"]["name"] if take else "The device"
                    self.start_error = ("device_no_audio",
                                        f"{name} opened but sent no audio.")
                if self.start_error is None:
                    self.start_error = w.error or (
                        "worker_failed", f"The recorder stopped at start (exit {code}).")
                self._end_failed_start(w)
                return
            if take is None:
                self.state = "idle"
                self.changed.notify_all()
                return
            for n in w.segments:
                seg = take.segment(n)
                if seg is not None and seg["start_frame"] is None:
                    # Opened but never got audio: nothing to place; drop it if empty.
                    self._drop_empty_segment(seg)
            if self.stop_reason is not None:
                self._finish(self.stop_reason)
            elif code == EXIT_DISK_FULL:
                self.emit("error", key="disk_full",
                          text="The disk is full. The take stopped; everything "
                               "recorded up to now is saved.")
                self._finish("disk_full")
            elif code == EXIT_DEVICE_LOST or w.lost_reason:
                self._device_lost(w.lost_reason or "lost")
            elif code == EXIT_OK:
                self._finish("stopped")
            else:
                self._worker_died(w, code)
            self.changed.notify_all()

    def _drop_empty_segment(self, seg: dict) -> None:
        take = self.take
        if any(f["frames"] for f in seg["files"].values()):
            take.place_segment(seg, take.last_end(before=seg["segment"]))
            return
        for f in seg["files"].values():
            with contextlib.suppress(OSError):
                (take.folder / f["file"]).unlink()
        take.data["segments"].remove(seg)
        if take.started:
            take.save()

    def _end_failed_start(self, w: Worker | None = None) -> None:
        take = self.take
        if take is not None and w is not None:
            for n in w.segments:
                seg = take.segment(n)
                if seg is not None and not take.segment_frames(seg):
                    for f in seg["files"].values():
                        with contextlib.suppress(OSError):
                            (take.folder / f["file"]).unlink()
        self.take = None
        self.state = "idle"
        self.keep_awake.stop()
        with contextlib.suppress(OSError):
            (self.state_dir / "current.json").unlink()
        self.changed.notify_all()

    def _device_lost(self, reason: str) -> None:
        take = self.take
        self.state = "device_lost"
        self.gap_reason = "device_lost"
        self.next_device_poll = time.monotonic() + self.device_poll
        name = take.data["device"]["name"]
        take.journal("device_lost", reason=reason, at_frame=take.last_end())
        take.save()
        log.warning("device lost (%s); waiting for %s to come back", reason, name)
        self.emit("device_lost", take=take.take, device=take.data["device"],
                  reason=reason, at_frame=take.last_end(),
                  text=f"{name} stopped sending audio. Recording continues as soon as "
                       "it is back.")

    def _worker_died(self, w: Worker, code: int) -> None:
        take = self.take
        if not w.flushed:
            self.failures += 1
        take.journal("worker_died", exit=code, segment=w.segment,
                     error=w.error[0] if w.error else None)
        if self.failures >= RESTART_LIMIT:
            key, text = w.error or ("worker_keeps_failing", "")
            self.emit("error", key="worker_keeps_failing",
                      text=f"The recorder failed {self.failures} times in a row and "
                           f"was not restarted ({key}: {text}). Everything recorded up "
                           "to now is saved.")
            self._finish("worker_keeps_failing")
            return
        take.data["worker_restarts"] += 1
        take.journal("worker_restarted", restarts=take.data["worker_restarts"])
        take.save()
        self.state = "restarting"
        self.gap_reason = "worker_restart"
        self.restart_at = time.monotonic() + min(
            5.0, self.restart_backoff * 2 ** self.failures)
        self.emit("worker_restarted", take=take.take, exit=code,
                  restarts=take.data["worker_restarts"],
                  text="The recording process stopped unexpectedly and is being "
                       "restarted; the gap is logged.")

    # --- stop -------------------------------------------------------------------

    def stop(self, reason: str, *, wait: bool) -> dict:
        with self.lock:
            if self.state in ("idle", "checking", *ARMED_STATES):
                raise ProtocolError("not_recording", "No take is recording.")
            take = self.take
            if self.stop_reason is None:
                self.stop_reason = reason
                self.stop_deadline = time.monotonic() + self.stop_timeout
            if self.worker is not None:
                self.state = "stopping"
                self.worker.send("stop")
            elif self.state != "idle":
                self._finish(reason)
            if wait:
                while self.take is take and take is not None:
                    self.changed.wait(1.0)
            return {"take": dict(self.last_take or {})}

    def _finish(self, reason: str) -> None:
        """End the take: files repaired and closed, snapshot final (lock held)."""
        take = self.take
        if take is None:
            return
        if self.worker is not None:
            self.worker.kill()
            self.worker = None
        for seg in take.data["segments"]:
            if seg["start_frame"] is None:
                take.place_segment(seg, take.last_end(before=seg["segment"]))
            seg["end"] = seg["end"] or reason
        take.data["state"] = "stopped"
        take.data["stop_reason"] = reason
        take.save()
        take.journal("stopped", reason=reason, frames=take.data["frames"])
        self.last_take = {"folder": str(take.folder), "take": take.take,
                          "stop_reason": reason, "frames": take.data["frames"],
                          "sidecar": str(take.sidecar)}
        self.emit("stopped", **self.last_take)
        log.info("take %s stopped (%s), %d frames", take.take, reason,
                 take.data["frames"])
        self.take = None
        self.state = "idle"
        self.stop_reason = None
        self.keep_awake.stop()
        with contextlib.suppress(OSError):
            (self.state_dir / "current.json").unlink()
        self.changed.notify_all()

    # --- the monitor ------------------------------------------------------------

    def _monitor(self) -> None:
        while not self.closed.wait(self.tick):
            try:
                self._monitor_once()
            except Exception:
                log.exception("monitor")

    def _idle_check(self, now: float) -> None:
        """Exit by itself when nothing needs the recorder: idle (no take, not listening)
        and no client connected for ``idle_exit`` seconds. A take, a listener or a
        connected editor resets the clock, so it can never exit under a recording."""
        if not self.idle_exit:
            return
        with self.lock:
            idle = (self.state == "idle" and self.take is None and self.armed is None
                    and not self.clients)
            if not idle:
                self._idle_since = None
                return
            if self._idle_since is None:
                self._idle_since = now
            elif now - self._idle_since >= self.idle_exit:
                log.info("idle with no editor for %.0f s: exiting", self.idle_exit)
                self.shutdown_requested.set()

    def _monitor_once(self) -> None:
        now = time.monotonic()
        with self.lock:
            state = self.state
            w = self.worker
            expired = state == "armed" and now > self.armed_until
        if expired:
            self.disarm("expired")  # nobody kept it armed: the microphone is let go
        self._idle_check(now)
        if state in ("recording", "restarting", "device_lost"):
            self._disk_tick()
        with self.lock:
            if self.state == "restarting" and self.worker is None and (
                    now >= self.restart_at):
                self._spawn(self.take.next_segment_number())
            if (self.state == "stopping" and self.worker is not None
                    and now > self.stop_deadline):
                log.warning("worker did not stop in time; killing it")
                self.worker.kill()
            if (self.state == "recording" and w is not None and w is self.worker
                    and now - w.last_heard > self.stuck_after):
                log.warning("worker silent for %.0f s; killing it", now - w.last_heard)
                if self.take is not None:
                    self.take.journal("worker_stuck", seconds=round(now - w.last_heard))
                w.kill()
            poll = self.state == "device_lost" and now >= self.next_device_poll
            if poll:
                self.next_device_poll = now + self.device_poll
                want = dict(self.params["device"])
        if poll:
            self._poll_device(want)

    def _poll_device(self, want: dict) -> None:
        try:
            device = resolve_device(self.list_devices(), {"name": want["name"]})
        except (SourceError, ProtocolError, OSError, ValueError,
                subprocess.SubprocessError):
            return
        with self.lock:
            if self.state != "device_lost" or self.take is None:
                return
            take = self.take
            self.params["device"] = {"index": device["index"], "name": device["name"]}
            take.journal("device_back", device=device)
            self.emit("device_back", take=take.take, device=device)
            log.info("device back: %s", device["name"])
            self.state = "restarting"
            self._spawn(take.next_segment_number())

    def _disk_tick(self) -> None:
        with self.lock:
            take = self.take
            if take is None:
                return
            bps = self.bytes_per_second()
            folder = take.folder
        try:
            free, seconds = self.disk_check(folder, bps)
        except OSError:
            return
        with self.lock:
            if self.take is not take:
                return
            self.disk_free_bytes, self.disk_seconds = free, seconds
            for limit in WARN_SECONDS:
                if seconds < limit and limit not in self.warned:
                    self.warned.add(limit)
                    take.journal("disk_low", seconds_left=round(seconds),
                                 free_bytes=free)
                    self.warn("disk_low",
                              f"About {max(1, round(seconds / 60))} minutes of "
                              "recording space left on the disk.",
                              seconds_left=round(seconds), free_bytes=free)
                elif seconds > limit + 60:
                    self.warned.discard(limit)
            if seconds <= STOP_SECONDS and self.stop_reason is None:
                take.journal("disk_full", seconds_left=round(seconds), free_bytes=free)
                self.emit("error", key="disk_full",
                          text="The disk is nearly full. The take was stopped; "
                               "everything recorded up to now is saved.")
                self.stop("disk_full", wait=False)


def recover_take(folder: Path, take: str, params: dict | None = None) -> dict:
    """Repair a take that no recorder is writing any more (after a crash).

    Every segment file on disk is repaired and the snapshot rebuilt from the
    files; a take still marked ``recording`` becomes ``interrupted``. Returns
    what was found per file.
    """
    sidecar = folder / naming.sidecar_file(take)
    if sidecar.exists():
        rec = TakeRecord.load(folder, take)
    elif params is not None:
        rec = TakeRecord.new(folder, take, rate=int(params["rate"]),
                             device=dict(params["device"]),
                             channels=list(params["channels"]),
                             names=list(params["names"]))
    else:
        raise ProtocolError("take_not_found", f"No take {take} in {folder}.")
    files = []
    on_disk = rec.files_on_disk()
    for n, found in sorted(on_disk.items()):
        seg = rec.segment(n)
        if seg is None:
            seg = rec.add_segment(n, found)
        for name, f in found.items():
            seg["files"].setdefault(name, {"file": f, "frames": 0})
        files += rec.repair_segment(seg)
    for seg in sorted(rec.data["segments"], key=lambda s: s["segment"]):
        if seg["start_frame"] is None:
            # A segment whose start was never logged: put it right after the one
            # before it, and say so (its true position is unknown).
            start = rec.last_end(before=seg["segment"])
            rec.place_segment(seg, start)
            seg["start_unknown"] = True
    rec.data["segments"] = [s for s in rec.data["segments"]
                            if s["segment"] in on_disk or rec.segment_frames(s)]
    was = rec.data["state"]
    if was == "recording":
        rec.data["state"] = "interrupted"
        rec.data["stop_reason"] = "recorder_crashed"
    rec.save()
    rec.journal("recovered", previous_state=was, files=files)
    log.info("recovered take %s in %s: %s", take, folder, files)
    return {"folder": str(folder), "take": take, "state": rec.data["state"],
            "frames": rec.data["frames"], "files": files, "sidecar": str(sidecar)}


def _recover(sup: Supervisor) -> None:
    current = sup.state_dir / "current.json"
    if not current.exists():
        return
    try:
        params = json.loads(current.read_text(encoding="utf-8"))
        result = recover_take(Path(params["folder"]), params["take"], params)
    except (OSError, ValueError, KeyError, ProtocolError) as e:
        log.exception("could not recover the interrupted take")
        result = {"error": str(e)}
    sup.recovered.append(result)
    with contextlib.suppress(OSError):
        current.unlink()

