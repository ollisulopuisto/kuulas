"""Running as the Kuulas.app bundle (WP73).

The bundle is a Briefcase app: Python is embedded and starts ``python -m kuulas``, which
calls :func:`main`. What differs from ``uv run kuulas``:

- there is no terminal, so output goes to ``~/Library/Logs/Kuulas/kuulas.log``;
- the minimal ``PATH`` of a double-clicked app has no Homebrew, so the bundled
  ``ffmpeg`` and ``ffprobe`` (``Contents/Resources/bin``) are put first;
- numba's compiled-code cache must not be written inside the signed bundle, which would
  change it after signing, so it goes to ``~/Library/Caches/Kuulas/numba``;
- Finder may add ``-psn_...`` to the arguments.

The functions are pure (paths and dicts in, paths and dicts out) and tested without a
bundle; only :func:`main` touches the process.
"""

from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from . import logsetup


def resources_dir(module_file: str | Path) -> Path | None:
    """``Contents/Resources`` when ``module_file`` is inside an app bundle
    (``Resources/app/kuulas/...``, Briefcase's layout), else None."""
    package = Path(module_file).resolve().parent
    app = package.parent
    if app.name == "app" and app.parent.name == "Resources":
        return app.parent
    return None


def environment(resources: Path, env: dict[str, str], home: Path) -> dict[str, str]:
    """``env`` with the bundled tools first on ``PATH`` and numba's cache moved out of
    the bundle (an explicit ``NUMBA_CACHE_DIR`` is kept)."""
    out = dict(env)
    path = [str(resources / "bin")]
    if env.get("PATH"):
        path.append(env["PATH"])
    out["PATH"] = os.pathsep.join(path)
    out.setdefault("NUMBA_CACHE_DIR",
                   str(home / "Library" / "Caches" / "Kuulas" / "numba"))
    return out


def log_file(home: Path, name: str = "kuulas.log") -> Path:
    return home / "Library" / "Logs" / "Kuulas" / name


def clean_argv(argv: list[str]) -> list[str]:
    """``argv`` without the program name and without Finder's ``-psn_`` argument."""
    return [a for a in argv[1:] if not a.startswith("-psn_")]


def wants_log(args: list[str]) -> bool:
    """Whether output goes to the log file. Not for ``--selftest``: the build script
    reads its report from the terminal, and ``--help`` is read there too."""
    return not any(a in ("--selftest", "--help", "-h") for a in args)


def recorder_args(args: list[str]) -> list[str] | None:
    """The recorder's arguments when the bundle was started as ``-m kuulas_recorder ...``,
    else None. The recorder (WP12a) starts itself and its workers with
    ``<sys.executable> -m kuulas_recorder``; in the app ``sys.executable`` is the bundle's
    launcher, which always runs ``python -m kuulas`` with the arguments it was given, so
    this module hands them on."""
    if args[:2] == ["-m", "kuulas_recorder"]:
        return args[2:]
    return None


def worker_args(args: list[str]) -> list[str] | None:
    """The transcription worker's arguments when the bundle was started as ``-m
    kuulas.transcribe_worker ...``, else None. ``bgjobs.start_worker_process`` runs
    ``<sys.executable> -m kuulas.transcribe_worker run <job file>``; in the app that
    executable is the launcher (see :func:`recorder_args`), so this module hands the
    arguments on. Without this the worker never started in the app and every background
    transcription showed as "interrupted"."""
    if args[:2] == ["-m", "kuulas.transcribe_worker"]:
        return args[2:]
    return None


def _run_worker(args: list[str]) -> int:
    """Run the worker's ``main`` (it never imports the editor session)."""
    from . import transcribe_worker  # noqa: PLC0415

    return transcribe_worker.main(args)


def _run_recorder(args: list[str]) -> int:
    """Run ``kuulas_recorder`` as its own ``__main__`` would (by name: the editor imports
    nothing of the recorder but its client)."""
    import runpy  # noqa: PLC0415

    sys.argv = ["kuulas_recorder", *args]
    try:
        runpy.run_module("kuulas_recorder", run_name="__main__", alter_sys=True)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return 0


def _open_log(home: Path, name: str = "kuulas.log"):
    """The log file, rotated (1 MB, 3 kept), also taking stdout, stderr and fatal
    crashes: a bundle has no terminal, so this file is all a tester can send. The
    transcription worker is its own process with its own file (``kuulas-worker.log``)."""
    file = log_file(home, name)
    file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(getattr(
        logging, logsetup.resolve(os.environ, logsetup.level_setting())))
    stream = open(file, "a", buffering=1, encoding="utf-8")  # noqa: SIM115 - open for the life of the process
    sys.stdout = sys.stderr = stream
    faulthandler.enable(stream)
    return file


def main() -> int:
    """The bundle's entry point (``python -m kuulas``)."""
    home = Path.home()
    resources = resources_dir(__file__)
    args = clean_argv(sys.argv)
    recorder = recorder_args(args)
    if recorder is not None:
        # Before the log is opened: the recorder's worker talks to its supervisor on
        # stdout, and the recorder keeps its own log (docs/RECORDER.md).
        if resources is not None:
            os.environ.update(environment(resources, dict(os.environ), home))
        return _run_recorder(recorder)
    worker = worker_args(args)
    if worker is not None:
        if resources is not None:
            os.environ.update(environment(resources, dict(os.environ), home))
            _open_log(home, "kuulas-worker.log")
        return _run_worker(worker)
    if resources is not None:
        os.environ.update(environment(resources, dict(os.environ), home))
        if wants_log(args):
            _open_log(home)
    from .build_info import build_label  # noqa: PLC0415
    from .cli import main as cli_main  # noqa: PLC0415

    logging.getLogger("kuulas").info("kuulas %s starting, argv %s", build_label(),
                                     args)
    return cli_main(args)
