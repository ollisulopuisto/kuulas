"""``kuulas --selftest``: a headless smoke check of an installed build (WP73).

Run by ``scripts/build_dmg.sh`` against the built app, and by a tester who wants to know
whether a build works at all. No window and no audio device: it checks that the libraries
load from where they are installed, that ffmpeg is found, that the UI files are served,
that a project opens and the server answers, and that the numba-compiled loudness meter
runs. The report lines are a fixed format for the build script to read, not user text, so
they are not translated: ``ok   <check>: <detail>`` / ``FAIL <check>: <error>``, then one
summary line.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

#: Imported to prove the compiled libraries and their bundled dylibs load.
LIBRARIES = ("numpy", "scipy", "numba", "pedalboard", "soundfile", "soxr", "lxml",
             "sounddevice", "speechmix", "nhsx", "silencelearn", "fastapi", "uvicorn")

TIMEOUT = 20


class SelftestError(Exception):
    """A failed check. Its text is a diagnostic line for the build script and for the
    bug report, in English like the rest of the report (see the module docstring)."""


def check_build() -> str:
    from .build_info import build_label  # noqa: PLC0415

    return build_label()


def check_libraries() -> str:
    for name in LIBRARIES:
        importlib.import_module(name)
    import soundfile  # noqa: PLC0415

    return f"{len(LIBRARIES)} imported, libsndfile {soundfile.__libsndfile_version__}"


def check_ffmpeg() -> str:
    from speechmix.binaries import get_binary_path  # noqa: PLC0415

    lines = []
    for tool in ("ffmpeg", "ffprobe"):
        path = get_binary_path(tool)
        done = subprocess.run(  # noqa: S603 - the tool speechmix found, fixed argument
            [path, "-version"], capture_output=True, text=True, timeout=TIMEOUT,
            check=True, stdin=subprocess.DEVNULL)
        lines.append(f"{done.stdout.splitlines()[0].split(' Copyright')[0]} ({path})")
    return "; ".join(lines)


def check_ui() -> str:
    from .server import UI_DIR  # noqa: PLC0415

    index = UI_DIR / "index.html"
    if not index.is_file():
        problem = f"no index.html in {UI_DIR}"
        raise SelftestError(problem)
    return str(UI_DIR)


def check_server() -> str:
    """A tiny project, opened as the window opens it: the same thread and app."""
    from .desktop import RunningProject  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="kuulas-selftest-") as tmp:
        running = RunningProject(str(Path(tmp) / "Selftest.kuulas"))
        try:
            with urllib.request.urlopen(running.url + "api/state",  # noqa: S310 - 127.0.0.1
                                        timeout=TIMEOUT) as r:
                state = json.loads(r.read())
            with urllib.request.urlopen(running.url, timeout=TIMEOUT) as r:  # noqa: S310
                page = r.read().decode("utf-8", "replace")
        finally:
            running.stop()
    if "<html" not in page.lower():
        problem = "the UI page was not served"
        raise SelftestError(problem)
    return f"/api/state answered ({len(state)} keys), UI page served"


def check_meter() -> str:
    """The loudness meter compiles with numba on first use: the library most likely to
    fail only once installed (a missing cache folder, a blocked JIT)."""
    import numpy as np  # noqa: PLC0415
    from speechmix.meter import IntegratedMeter  # noqa: PLC0415

    rate = 48000
    t = np.arange(rate * 2) / rate
    meter = IntegratedMeter(rate)
    meter.add(0.1 * np.sin(2 * np.pi * 440 * t))
    value = meter.value()
    if value is None or not -40 < value < 0:
        problem = f"implausible loudness {value}"
        raise SelftestError(problem)
    return f"{value:.1f} LUFS for a 440 Hz sine at 0.1"


def check_recorder() -> str:
    """The recorder (WP12a) starts from this installation as its own process and records
    one second from its fake source (no microphone, no permission prompt): proof that the
    bundle can start ``python -m kuulas_recorder`` and its worker."""
    if sys.platform == "win32":
        return "not supported on Windows (recorder uses Unix sockets)"
    import os  # noqa: PLC0415
    import time  # noqa: PLC0415

    from kuulas_recorder.client import RecorderClient, spawn_supervisor  # noqa: PLC0415

    # A short folder: a socket path must stay under 104 bytes on macOS.
    with tempfile.TemporaryDirectory(prefix="kr", dir="/tmp") as tmp:
        root = Path(tmp)
        spec = root / "fake.json"
        spec.write_text(json.dumps({
            "devices": [{"index": 0, "name": "Selftest", "channels": 1,
                         "default_rate": 48000.0, "hostapi": "fake", "default": True}],
            "epoch_ns": time.monotonic_ns()}), encoding="utf-8")
        env = {**os.environ, "KUULAS_RECORDER_FAKE": str(spec)}
        sock = root / "s.sock"
        proc = spawn_supervisor(sock, state_dir=root / "state", env=env)
        try:
            with RecorderClient.connect(sock, timeout=TIMEOUT) as rec:
                rec.request("start", folder=str(root), take="Take 1", channels=[1],
                            names=["Selftest"])
                time.sleep(1.0)
                take = rec.request("stop")["take"]
                rec.request("quit")
            proc.wait(timeout=TIMEOUT)
        finally:
            if proc.poll() is None:
                proc.kill()
        if take["frames"] < 48000 // 2:
            problem = f"only {take['frames']} frames recorded in a second"
            raise SelftestError(problem)
    return f"{take['take']}: {take['frames']} frames, {take['stop_reason']}"


def check_worker() -> str:
    """The transcription worker (WP79) starts from this installation, as the editor starts
    it, and runs a job with the ``selftest`` backend (no engine, no audio, no network) to
    ``completed``. In the app ``sys.executable`` is the bundle's launcher, not a Python:
    this is the check that a background transcription can run at all (it did not, once:
    every job showed as interrupted)."""
    import time  # noqa: PLC0415

    from . import bgjobs, colab_transcribe  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="kuulas-selftest-") as tmp:
        folder = Path(tmp) / "Selftest.kuulas"
        job_id = bgjobs.create_job(
            folder, backend="selftest",
            items=[{"id": "m0", "name": "selftest", "path": "selftest.wav"}],
            previous={}, names=["selftest"], model=None, language=None, settings=None)
        bgjobs.start_worker_process(bgjobs.job_file(folder, job_id))
        deadline = time.monotonic() + 3 * TIMEOUT
        status: dict = {}
        while time.monotonic() < deadline:
            status = bgjobs.read_json(bgjobs.status_file(folder, job_id)) or {}
            if status.get("state") in bgjobs.FINISHED:
                break
            time.sleep(0.1)
        if status.get("state") != "completed":
            problem = (f"the worker did not complete the job (state "
                       f"{status.get('state')}, pid {status.get('pid')}, "
                       f"error {status.get('error')})")
            raise SelftestError(problem)
        words = colab_transcribe.read_words_json(
            bgjobs.result_file(folder, job_id, "m0"))["words"]
    return f"completed, {len(words)} word(s) in the result file"


def check_tools() -> str:
    """Where the programs Colab transcription needs are found with the PATH an app
    started from Finder has. Information only: a missing one is reported when a job
    needs it, with the command and the folder (``error.colab.not_found``)."""
    import os  # noqa: PLC0415

    from . import bundle, colab_signin, colab_transcribe, toolpath  # noqa: PLC0415
    from .messages import t  # noqa: PLC0415

    program = colab_transcribe.default_command()[0]
    found = toolpath.resolve(program)
    parts = [f"{program}: {found or 'not found'}",
             f"colab: {toolpath.resolve('colab') or 'not found'}",
             f"google sign-in: {'yes' if colab_signin.signed_in() else 'no'}",
             f"PATH has {len(toolpath.search_path(os.environ).split(os.pathsep))}"
             " folders"]
    resources = bundle.resources_dir(__file__)
    if resources is not None:
        for name in ("uv", "uvx"):
            tool = resources / "bin" / name
            if not tool.is_file():
                problem = t("error.selftest.tool_missing", name=name)
                raise SelftestError(problem)
            done = subprocess.run(  # noqa: S603 - exact path inside this bundle
                [str(tool), "--version"], capture_output=True, text=True,
                timeout=TIMEOUT, check=False, stdin=subprocess.DEVNULL,
                env={**os.environ, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"})
            if done.returncode != 0 or not done.stdout.startswith(f"{name} "):
                problem = t("error.selftest.tool_failed", name=name,
                            error=done.stderr.strip())
                raise SelftestError(problem)
            parts.append(done.stdout.strip())
    return "; ".join(parts)


def _in_bundle() -> bool:
    from . import bundle  # noqa: PLC0415

    return bundle.resources_dir(__file__) is not None


def check_automixer() -> str:
    """The bundled automixer starts as Kuulas starts it (the launcher with ``-m
    automixer``) and answers ``--help`` with its usage: its package and every library
    its command line imports load from the bundle. From source there is no bundled one
    (Kuulas then runs ``uv run automixer`` in the podcast checkout): information only."""
    from . import automix  # noqa: PLC0415

    command = automix.bundled_command()
    if not _in_bundle():
        return "not bundled (running from source: the settings or uv run in the checkout)"
    if command is None:
        problem = "the automixer package is not in the bundle"
        raise SelftestError(problem)
    done = subprocess.run(  # noqa: S603 - the bundle's own launcher, fixed arguments
        [*command, "--help"], capture_output=True, text=True, timeout=3 * TIMEOUT,
        check=False, stdin=subprocess.DEVNULL)
    out = done.stdout + done.stderr
    if done.returncode != 0 or "usage: automixer" not in out:
        last = (out.strip().splitlines() or ["no output"])[-1]
        problem = f"automixer --help exited {done.returncode}: {last}"
        raise SelftestError(problem)
    flags = [f for f in ("--keep-music-level", "--events", "--progress") if f in out]
    return f"--help answered ({' '.join(flags) or 'no gated flags'})"


#: In the order they run; each is the function ``check_<name>`` in this module, looked
#: up when it runs (so a test can replace one).
CHECKS = ("build", "libraries", "ffmpeg", "ui", "server", "meter", "recorder", "worker",
          "analysis_worker", "automixer", "tools")


def check_analysis_worker() -> str:
    """The analysis worker (``offload``, docs/PLAYBACK-PRIORITY.md) starts from this
    installation as the editor starts it, and runs at its lowered priority
    (``offload.WORKER_NICE``). Without it Auto-Silence and the loudness curves fall
    back to the editor process, where they compete with playback."""
    if sys.platform == "win32":
        return "priority controls are not available on Windows"
    from . import offload  # noqa: PLC0415

    info = offload.probe({"what": "priority"}, pause=False)
    nice = info.get("nice")
    if nice != offload.WORKER_NICE:
        problem = f"the analysis worker runs at nice {nice}, not {offload.WORKER_NICE}"
        raise SelftestError(problem)
    return f"nice {info['nice']}, darwin background {info.get('darwin_background')}"


def run() -> int:
    """Run every check, print one line each, return 0 when all passed."""
    failed = 0
    for name in CHECKS:
        try:
            print(f"ok   {name}: {globals()[f'check_{name}']()}", flush=True)
        except Exception as e:  # noqa: BLE001 - every failure is a line in the report
            failed += 1
            print(f"FAIL {name}: {type(e).__name__}: {e}", flush=True)
    print("selftest passed" if not failed else f"selftest FAILED ({failed})", flush=True)
    return 1 if failed else 0
