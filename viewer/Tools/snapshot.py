"""Reference snapshot algorithm for the native reader; never open source SQLite.

SQLite read-only WAL connections can create sidecar files. Copy only DB and WAL
into a private directory, then let SQLite validate/recover the private copy.
Reject a source changing during the copy; never use immutable on a live project.
"""
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path


class UnstableSnapshotError(RuntimeError):
    """The source changed or disappeared while reading it."""


def _signature(root):
    result = []
    for name in ('project.sqlite', 'project.sqlite-wal'):
        try:
            st = (root / name).stat()
            result.append((name, st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns,
                           st.st_ctime_ns))
        except FileNotFoundError:
            result.append((name, None))
    return result


@contextmanager
def snapshot(project):
    """Yield a transaction on a private coherent snapshot, or fail closed.

    The source may be a package on a genuinely read-only volume. A caller may
    retry explicitly after an unstable copy; this function does not spin.
    """
    project = Path(project)
    before = _signature(project)
    with tempfile.TemporaryDirectory(prefix='kuulas-viewer-') as temporary:
        target = Path(temporary)
        for name in ('project.sqlite', 'project.sqlite-wal'):
            source = project / name
            if source.exists():
                shutil.copyfile(source, target / name)
        if before != _signature(project):
            raise UnstableSnapshotError('Project changed during snapshot')
        db = sqlite3.connect(target / 'project.sqlite')
        try:
            db.execute('pragma query_only=on')
            db.execute('begin')
            # SQLite handles WAL salts, checksums and commit boundaries. Do not
            # interpret a copied WAL by hand or silently ignore its failure.
            if db.execute('pragma quick_check').fetchone() != ('ok',):
                raise UnstableSnapshotError('Invalid database snapshot')
            yield db
        finally:
            db.close()
