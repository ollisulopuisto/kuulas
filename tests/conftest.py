"""Shared test setup."""

import getpass
import os
import tempfile
from pathlib import Path

import pytest

from kuulas import messages


def _writable(path: Path) -> bool:
    """Can we create and delete a file in ``path`` (creating it if needed)?"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_text("ok")
        probe.unlink()
    except OSError:
        return False
    return True


def _numba_cache_dir() -> Path:
    """A writable Numba cache folder, chosen before Numba is imported.

    The mastering tests compile Numba kernels. On a clean machine or in a
    restricted sandbox the default cache next to the source is not writable.
    An explicit ``NUMBA_CACHE_DIR`` is used if it works; otherwise a per-user
    folder in the temp directory (per user, so one account's folder never
    blocks or poisons another's).
    """
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = "shared"
    for candidate in (os.environ.get("NUMBA_CACHE_DIR"),
                      Path(tempfile.gettempdir()) / f"kuulas-numba-{user}"):
        if candidate and _writable(Path(candidate)):
            return Path(candidate)
    raise RuntimeError("no writable folder for the Numba cache; set NUMBA_CACHE_DIR")


os.environ["NUMBA_CACHE_DIR"] = str(_numba_cache_dir())


@pytest.fixture(autouse=True)
def _english_messages():
    """Every test starts in English and leaves the language as it found it.

    The default language follows the machine (Finnish on the owner's Mac), and
    ``set_language`` is process-wide, so without this a test that asserts
    English text passes or fails depending on which test ran before it.
    Tests that need Finnish call ``set_language("fi")`` themselves.
    """
    before = messages.language()
    messages.set_language("en")
    try:
        yield
    finally:
        messages.set_language(before)


@pytest.fixture(autouse=True)
def _playback_gate(monkeypatch):
    """Every test starts with a fresh playback gate (no engine watched, no input),
    and heavy analysis runs inline: no test starts the analysis worker process by
    accident (``tests/test_analysis_worker.py`` starts it on purpose)."""
    from kuulas import offload, priority  # noqa: PLC0415 - after NUMBA_CACHE_DIR

    monkeypatch.setattr(offload, "MODE", "inline")
    priority.GATE.reset()
    yield
    priority.GATE.reset()


@pytest.fixture(autouse=True)
def _private_clipboard(tmp_path_factory, monkeypatch):
    """The clipboard history is a per-user file: no test may touch the real one."""
    folder = tmp_path_factory.mktemp("clipboard")
    monkeypatch.setenv("KUULAS_CLIPBOARD_FILE", str(folder / "clipboard.json"))


@pytest.fixture(autouse=True)
def _private_recents(tmp_path_factory, monkeypatch):
    """The recent projects are a per-user file: no test may read the real one."""
    folder = tmp_path_factory.mktemp("recents")
    monkeypatch.setenv("KUULAS_RECENTS_FILE", str(folder / "recent.json"))


@pytest.fixture(autouse=True)
def _private_app_settings(tmp_path_factory, monkeypatch):
    """The app settings (language) are a per-user file: no test may read the real one."""
    folder = tmp_path_factory.mktemp("settings")
    monkeypatch.setenv("KUULAS_SETTINGS_FILE", str(folder / "settings.json"))


@pytest.fixture(autouse=True)
def _private_series(tmp_path_factory, monkeypatch):
    """The series library is a per-user folder: no test may touch the real one."""
    monkeypatch.setenv("KUULAS_SERIES_DIR", str(tmp_path_factory.mktemp("series")))


@pytest.fixture(autouse=True)
def _private_view_memory(tmp_path_factory, monkeypatch):
    """The remembered views are a per-user file: no test may touch the real one."""
    folder = tmp_path_factory.mktemp("view-memory")
    monkeypatch.setenv("KUULAS_VIEW_MEMORY_FILE", str(folder / "view-memory.json"))


@pytest.fixture(autouse=True)
def _signed_in_to_colab(tmp_path_factory, monkeypatch):
    """Colab sign-in is a file in the user's config; a test never reads the real one.
    Signed in by default (tests of the sign-in point ``KUULAS_COLAB_TOKEN`` elsewhere)."""
    token = tmp_path_factory.mktemp("colab-token") / "token.json"
    token.write_text('{"refresh_token": "test"}', encoding="utf-8")
    monkeypatch.setenv("KUULAS_COLAB_TOKEN", str(token))


@pytest.fixture(autouse=True)
def _inline_transcription_worker(monkeypatch):
    """A background transcription job (WP79) runs in a thread of the test process,
    so no test starts a detached process by accident and a test can patch the
    engine (``kuulas.transcribe.local``). Tests of the real worker program start it
    themselves (tests/test_transcribe_worker.py)."""
    import threading  # noqa: PLC0415

    from kuulas import bgjobs  # noqa: PLC0415
    from kuulas.transcribe_worker import run_job  # noqa: PLC0415

    def launch(path):
        threading.Thread(target=run_job, args=(path,), kwargs={"status_interval": 0},
                         daemon=True).start()

    monkeypatch.setattr(bgjobs, "launch_worker", launch)


@pytest.fixture(autouse=True)
def _isolated_orukeet_setting(tmp_path_factory, monkeypatch):
    """Tests never read or change the user's selected transcription model."""
    folder = tmp_path_factory.mktemp("orukeet-setting")
    monkeypatch.setenv("KUULAS_ORUKEET_FILE", str(folder / "model.json"))
