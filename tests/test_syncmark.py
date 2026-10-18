"""Keeping rebuildable and half-written files out of Dropbox (docs/FORMAT.md)."""

import subprocess
from pathlib import Path

from kuulas import syncmark


class Recorder:
    def __init__(self, fail: type[BaseException] | None = None):
        self.calls: list[list[str]] = []
        self.fail = fail

    def __call__(self, cmd, **kwargs):
        if self.fail:
            if self.fail is subprocess.TimeoutExpired:
                raise self.fail("xattr", 5)
            raise self.fail("no")
        self.calls.append(list(cmd))


def folder(tmp_path: Path) -> Path:
    root = tmp_path / "A.kuulas"
    (root / "caches").mkdir(parents=True)
    (root / "locks").mkdir()
    (root / "project.sqlite-wal").write_text("")
    (root / "project.sqlite-shm").write_text("")
    return root


def test_marks_the_side_files_and_caches_but_never_locks(tmp_path):
    root = folder(tmp_path)
    run = Recorder()
    syncmark.mark_package(root, run=run, platform="darwin")
    marked = {Path(c[-1]).name for c in run.calls}
    assert marked == {"project.sqlite-wal", "project.sqlite-shm", "caches"}
    for c in run.calls:
        assert c[:4] == ["xattr", "-w", "com.dropbox.ignored", "1"]
    assert not any("locks" in c[-1] for c in run.calls)


def test_skips_paths_that_do_not_exist(tmp_path):
    root = folder(tmp_path)
    (root / "project.sqlite-shm").unlink()
    run = Recorder()
    syncmark.mark_package(root, run=run, platform="darwin")
    assert {Path(c[-1]).name for c in run.calls} == {"project.sqlite-wal", "caches"}


def test_does_nothing_off_macos(tmp_path):
    run = Recorder()
    syncmark.mark_package(folder(tmp_path), run=run, platform="linux")
    assert run.calls == []


def test_a_missing_or_failing_xattr_is_silent(tmp_path):
    root = folder(tmp_path)
    for err in (FileNotFoundError, OSError):
        syncmark.mark_package(root, run=Recorder(fail=err), platform="darwin")
    syncmark.mark_package(root, run=Recorder(fail=subprocess.TimeoutExpired),
                          platform="darwin")
