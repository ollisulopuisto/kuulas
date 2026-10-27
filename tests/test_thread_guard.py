"""No thread or thread pool in the editor bypasses the playback gate (owner rule,
docs/PLAYBACK-PRIORITY.md): background work must never compete with playback.

Every ``ThreadPoolExecutor(...)``, ``ProcessPoolExecutor(...)`` and
``threading.Thread(...)`` constructed under ``src/kuulas`` is either made by
``priority.py`` (``priority.executor``, ``priority.gated_map``,
``priority.thread``: background marking, low QoS, the gate) or listed below with
the reason it may run while audio plays. The engine is the audio path itself and
is not scanned. A new raw thread fails this test until it is routed or listed.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "kuulas"

#: Not scanned: the audio path itself, and the gate.
EXEMPT_FILES = {"engine.py", "priority.py"}

#: (file, enclosing function as ``Class.method`` or ``function``) -> why this
#: thread may run while audio plays.
ALLOWED = {
    ("meter.py", "LiveShortTerm.read"):
        "the live audio-meter path: bounded device-output blocks measured at low QoS; "
        "it must run during playback to display current loudness, never project analysis",
    ("profiler.py", "Profiler.start"):
        "the performance report's sampler: it exists to watch a slow moment, sleeps "
        "between samples and is not paused by the gate it measures",
    ("server.py", "create_app"):
        "the live channel's one-thread reader of the engine status: the playhead "
        "never waits for playback priority",
    ("cli.py", "open_project"):
        "waits for the server to accept connections, then opens the browser; no work",
    ("package.py", "Package.start"):
        "heartbeat: a WAL checkpoint and a backup every few minutes; IO only",
    ("media.py", "_ffmpeg_pcm.__init__"):
        "decoder subprocess stderr drain and watchdog: IO waits, no compute",
    ("offload.py", "_watch_progress"):
        ("polls the analysis worker's progress file and relays status updates; "
         "IO only"),
    ("session.py", "Session.__init__"):
        "polls background-transcription status files every few seconds; no compute",
    ("automix.py", "run_process"):
        "reads the automixer subprocess log lines; IO only",
    ("record_session.py", "RecordSession.__init__"):
        "the recorder watcher: the recorder outranks playback (holiest, rule 17)",
    ("record_session.py", "RecordSession._import_later"):
        "takes a finished take in under the session lock: pausing it would block edits",
    ("colab_signin.py", "SigninFlow.start"):
        "reads the sign-in subprocess output; IO only",
    ("desktop.py", "RunningProject.__init__"):
        "the HTTP server thread: request handling, which the UI waits for",
    ("desktop.py", "Bridge.open_project"):
        "writes the recent-projects size summary once; IO only",
    ("desktop.py", "make_open_files_method"):
        "hands Finder's open request on; no work",
    ("transcribe_worker.py", "run_job"):
        "the detached worker's cancel watcher; a separate low-priority process",
}

CONSTRUCTORS = {"ThreadPoolExecutor", "ProcessPoolExecutor", "Thread"}


def _name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def raw_threads() -> list[tuple[str, str, int]]:
    found = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name in EXEMPT_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(SRC).as_posix()

        def visit(node, where, rel=rel, cls=None):
            for child in ast.iter_child_nodes(node):
                inner, inner_cls = where, cls
                if isinstance(child, ast.ClassDef) and where is None:
                    inner_cls = child.name
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    # The outermost function names the site: nested helpers
                    # (a ``def later`` inside ``open_project``) belong to it.
                    inner = where or (f"{cls}.{child.name}" if cls else child.name)
                if isinstance(child, ast.Call) and _name(child.func) in CONSTRUCTORS:
                    found.append((rel, where or "<module>", child.lineno))
                visit(child, inner, rel, inner_cls)

        visit(tree, None)
    return found


def test_every_raw_thread_is_routed_or_listed_with_a_reason():
    unrouted = [f"{f}:{line} in {fn}" for f, fn, line in raw_threads()
                if (f, fn) not in ALLOWED]
    assert unrouted == [], ("threads that bypass the playback gate; use "
                            "priority.executor/gated_map/thread or list them in "
                            f"ALLOWED with a reason: {unrouted}")


def test_the_allow_list_has_no_stale_entries():
    sites = {(f, fn) for f, fn, _ in raw_threads()}
    stale = sorted(set(ALLOWED) - sites)
    assert stale == []


def test_analysis_has_no_pool_of_its_own():
    text = (SRC / "analysis.py").read_text(encoding="utf-8")
    assert "ThreadPoolExecutor" not in text
    assert "priority.gated_map" in text
