"""``kuulas-recorder``: the command line (docs/RECORDER.md, "Running it").

    kuulas-recorder serve            run the supervisor (the editor starts it)
    kuulas-recorder devices [--json] list the input devices
    kuulas-recorder repair FILE...   repair WAVs left by a crash
    kuulas-recorder send CMD [JSON]  send one protocol command, print the answer
    kuulas-recorder watch [--levels] print the events as they come
    kuulas-recorder worker           internal: the audio process the supervisor runs

Everything printed is plain English for logs; the editor translates events by
their keys.
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import signal
import sys
import time
from pathlib import Path

from kuulas_recorder import transport as transport_mod


def _serve(args) -> int:
    from kuulas_recorder.supervisor import ProtocolError, Supervisor  # noqa: PLC0415

    sock = Path(args.socket) if args.socket else transport_mod.default_socket_path()
    state = Path(args.state_dir) if args.state_dir else sock.parent
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    handler = logging.handlers.RotatingFileHandler(
        state / "recorder.log", maxBytes=5 * 1024 * 1024, backupCount=3)
    # Log times are UTC and say so (the owner's rule: a time carries its zone).
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(message)s",
                            datefmt="%Y-%m-%dT%H:%M:%SZ")
    fmt.converter = time.gmtime
    handler.setFormatter(fmt)
    root = logging.getLogger("kuulas_recorder")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None and sys.stderr.isatty():
        root.addHandler(logging.StreamHandler())
    sup = Supervisor(sock, state, flush_seconds=args.flush_seconds,
                     max_data_bytes=args.max_data_bytes,
                     idle_exit=args.idle_exit)

    def on_signal(signum, _frame):
        root.info("signal %d: stopping the take cleanly and exiting", signum)
        sup.request_shutdown()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)  # a closed terminal is not a stop
    try:
        sup.open()
    except ProtocolError as e:
        print(e.text, file=sys.stderr)
        return 1
    sup.wait_for_shutdown()
    return 0


def _devices(args) -> int:
    from kuulas_recorder.sources import input_devices  # noqa: PLC0415

    devs = input_devices()
    if args.json:
        print(json.dumps(devs))
        return 0
    for d in devs:
        mark = "*" if d.get("default") else " "
        print(f"{mark} {d['index']:3d}  {d['name']}  ({d['channels']} in, "
              f"{round(d['default_rate'])} Hz, {d['hostapi']})")
    if not devs:
        print("No input devices.")
    return 0


def _repair(args) -> int:
    from kuulas_recorder.wavfile import WavRepairError, repair_wav  # noqa: PLC0415

    code = 0
    for f in args.files:
        try:
            r = repair_wav(f, rate=args.rate)
        except (OSError, WavRepairError) as e:
            print(f"{f}: {e}")
            code = 1
            continue
        what = "repaired" if r.changed else "fine"
        print(f"{f}: {what}, {r.frames} frames ({r.frames / args.rate:.1f} s)")
    return code


def _client(args):
    from kuulas_recorder.client import RecorderClient  # noqa: PLC0415

    return RecorderClient.connect(args.socket)


def _send(args) -> int:
    from kuulas_recorder.client import RecorderError  # noqa: PLC0415

    params = json.loads(args.json) if args.json else {}
    with _client(args) as c:
        try:
            answer = c.request(args.cmd, **params)
        except RecorderError as e:
            print(json.dumps({"ok": False, "error": {"key": e.key, "text": e.text}}))
            return 1
    print(json.dumps(answer, indent=1))
    return 0


def _watch(args) -> int:
    with _client(args) as c:
        hello = c.request("hello", subscribe=True, levels=args.levels)
        print(json.dumps(hello["status"]))
        try:
            while not c.closed:
                ev = c.next_event(1.0)
                if ev is not None:
                    print(json.dumps(ev), flush=True)
        except KeyboardInterrupt:
            pass
    return 0


def _worker(_args) -> int:
    from kuulas_recorder import worker  # noqa: PLC0415

    return worker.main()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kuulas-recorder",
                                description="The kuulas standalone recorder.")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("serve", help="run the recorder (supervisor)")
    s.add_argument("--socket", help="socket path (default: the per-user path)")
    s.add_argument("--state-dir", help="folder for the log and lock files")
    s.add_argument("--flush-seconds", type=float, default=1.0,
                   help="audio between flushes (default 1 s)")
    s.add_argument("--idle-exit", type=float, default=60.0,
                   help="exit after this many seconds idle with no client (0: never)")
    s.add_argument("--max-data-bytes", type=int, default=None, help=argparse.SUPPRESS)
    s.set_defaults(fn=_serve)
    d = sub.add_parser("devices", help="list input devices")
    d.add_argument("--json", action="store_true")
    d.set_defaults(fn=_devices)
    r = sub.add_parser("repair", help="repair WAV files left by a crash")
    r.add_argument("files", nargs="+")
    r.add_argument("--rate", type=int, default=48000)
    r.set_defaults(fn=_repair)
    c = sub.add_parser("send", help="send one command, print the answer")
    c.add_argument("cmd")
    c.add_argument("json", nargs="?", help="the command's fields as a JSON object")
    c.add_argument("--socket")
    c.set_defaults(fn=_send)
    w = sub.add_parser("watch", help="print events")
    w.add_argument("--levels", action="store_true")
    w.add_argument("--socket")
    w.set_defaults(fn=_watch)
    k = sub.add_parser("worker", help=argparse.SUPPRESS)
    k.set_defaults(fn=_worker)
    args = p.parse_args(argv)
    return int(args.fn(args) or 0)
