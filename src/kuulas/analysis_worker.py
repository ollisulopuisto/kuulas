"""The analysis worker: ``python -m kuulas.analysis_worker <task> <result>``.

Started by ``offload.call`` for one task and gone when it is done. Its first act
is nice ``offload.WORKER_NICE`` (10). Not nice 19 and the Darwin background
band any more: on a loaded Mac that starved it and it never finished (owner's
ps, 2026-10-20). It yields to playback by being stopped (SIGSTOP) while audio
plays when its caller is background work, and it has its own GIL. It exits
when the editor is gone (its parent changes, or the pipe on its stdin closes).
It reopens the project's media read-only and never opens the project's history:
it reads a pickled snapshot and writes a pickled answer
(``{"value": ...}`` or ``{"error": {...}}``), atomically.
"""

from __future__ import annotations

import os
import pickle
import sys
import time
import traceback
from pathlib import Path

from . import priority
from .offload import PIPE_ENV, WORKER_NICE


def _lower() -> dict:
    return priority.lower_this_process(darwin_background=False, nice=WORKER_NICE)


def _probe(what: dict, lowered: dict | None) -> dict:
    kind = what.get("what")
    if kind == "priority":
        return {**(lowered or {}), "nice": os.getpriority(os.PRIO_PROCESS, 0),
                "pid": os.getpid()}
    if kind == "spin":
        # CPU time, not wall time: a stopped worker spins no further.
        # ``beat``: a file the count is written to every ~10 ms, so a test can
        # see the worker make no progress while it is stopped.
        want = float(what.get("seconds", 0.1))
        beat = Path(what["beat"]) if what.get("beat") else None
        wall, cpu = time.monotonic(), time.process_time()
        count, last = 0, 0.0
        while time.process_time() - cpu < want:
            count += 1
            if beat is not None and time.monotonic() - last > 0.01:
                last = time.monotonic()
                beat.write_text(str(count), encoding="utf-8")
        return {"spun": time.process_time() - cpu, "wall": time.monotonic() - wall}
    raise ValueError(kind)


def open_store(spec: dict):
    """The project's media, read-only, with the editor's resolved linked paths."""
    from .media import MediaStore  # noqa: PLC0415 - after nice 19 (see the module doc)

    store = MediaStore(spec["folder"], spec["rate"], db=spec["db"],
                       cache_root=spec["cache_root"], read_only=True,
                       package_root=spec["package_root"],
                       series_root=spec.get("series_root"),
                       preferences=spec.get("preferences"), resolve=False)
    store._resolved_paths.update(spec.get("resolved") or {})
    store._linked_ok.update(spec.get("linked_ok") or {})
    return store


def run_task(payload: dict, lower: bool = False) -> dict:
    """One task to its reply. Never raises: the editor gets the error.
    ``lower``: take the worker's priority (the probe reports what took effect)."""
    from .messages import KuulasError  # noqa: PLC0415

    try:
        if payload["task"] == "_probe":
            lowered = _lower() if lower else None
            return {"value": _probe(payload["probe"], lowered)}
        from . import offload  # noqa: PLC0415

        fn = offload.resolve(payload["task"])
        store = open_store(payload["store"])
        try:
            value = fn(payload["project"], store, *payload.get("args", ()),
                       **payload.get("kwargs", {}))
        finally:
            store.close()
    except KuulasError as e:
        return {"error": {"key": e.key, "params": e.params, "text": str(e),
                          "module": type(e).__module__, "cls": type(e).__qualname__}}
    except Exception as e:  # noqa: BLE001 - every failure goes back to the editor
        traceback.print_exc(file=sys.stderr)
        return {"error": {"text": f"{type(e).__name__}: {e}"}}
    return {"value": value}


#: How often the worker checks that the editor still runs.
PARENT_CHECK_S = float(os.environ.get("KUULAS_PARENT_CHECK_S", "1.0"))


def watch_parent(parent: int | None = None, check_s: float | None = None) -> None:
    """Exit at once when the editor that started this worker is gone: nobody
    would read the answer, and an orphan only holds memory (owner's btop,
    2026-10-20). A stopped worker cannot look; ``offload.spawn_options`` and
    ``offload.sweep_orphans`` cover that case."""
    parent = os.getppid() if parent is None else parent
    check_s = PARENT_CHECK_S if check_s is None else check_s

    def watch() -> None:
        while True:
            # Parent 1 (launchd, init): the editor was gone before we looked.
            now = os.getppid()
            if now != parent or now == 1:
                os._exit(4)
            time.sleep(check_s)

    priority.thread(watch, "kuulas-worker-parent").start()


def watch_pipe() -> None:
    """Exit when the editor's end of the pipe on stdin closes (the editor
    exited or crashed): only when the editor said it holds one (``PIPE_ENV``);
    a worker started by hand has no such pipe."""
    if os.environ.get(PIPE_ENV) != "1":
        return

    def watch() -> None:
        # The raw descriptor, not sys.stdin: a daemon thread blocked in a
        # buffered read holds its lock, and interpreter shutdown aborts on it.
        try:
            while os.read(0, 4096):
                pass
        except OSError:
            pass
        os._exit(5)

    priority.thread(watch, "kuulas-worker-pipe").start()


def main(argv: list[str] | None = None) -> int:
    _lower()
    watch_parent()
    watch_pipe()
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python -m kuulas.analysis_worker <task file> <result file>",
              file=sys.stderr)
        return 2
    task, result = Path(args[0]), Path(args[1])
    payload = pickle.loads(task.read_bytes())  # noqa: S301 - the editor wrote it for us
    reply = run_task(payload, lower=True)
    partial = result.with_name(result.name + ".partial")
    partial.write_bytes(pickle.dumps(reply, protocol=pickle.HIGHEST_PROTOCOL))
    partial.replace(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
