"""Moving the old per-user clipboard history into its projects (WP65 step 3)."""

import json
import os
import socket

from kuulas.clipboard import ClipRef, Entry
from kuulas.clipboard_store import ClipboardStore, default_path, project_path
from kuulas.session import Session


def entry(n: int, source: str = "", shared: bool = False, created: float | None = None):
    return Entry(f"e{n:04d}", f"name {n}", float(n) if created is None else created,
                 refs=(ClipRef("a" * 64, 0, 100),), span=(0, 100),
                 source_project=source, shared=shared)


def seed(*entries):
    """Put entries into the per-user file, the way the old history held them."""
    store = ClipboardStore(default_path())
    for item in entries:
        store.update(lambda h, item=item: h.add(item))


def ids(store):
    return [e.id for e in store.load().entries()]


def open_project(tmp_path, name="One"):
    return Session(tmp_path / f"{name}.kuulas")


def test_entries_of_this_project_move_and_the_others_stay(tmp_path):
    one, two = tmp_path / "One.kuulas", tmp_path / "Two.kuulas"
    seed(entry(1, str(one)), entry(2, str(two)), entry(3, ""), entry(4, str(one)),
         entry(5, "/gone/Elsewhere.kuulas"))
    s = open_project(tmp_path)
    try:
        assert ids(s.clipboard) == ["e0004", "e0001"]  # newest first
        assert ids(s.shared_clipboard) == ["e0005", "e0003", "e0002"]
        assert (one / "clipboard.json").is_file()
    finally:
        s.close()


def test_the_other_project_gets_its_own_when_it_opens(tmp_path):
    one, two = tmp_path / "One.kuulas", tmp_path / "Two.kuulas"
    seed(entry(1, str(one)), entry(2, str(two)))
    open_project(tmp_path, "One").close()
    s = open_project(tmp_path, "Two")
    try:
        assert ids(s.clipboard) == ["e0002"]
        assert ids(s.shared_clipboard) == []
    finally:
        s.close()


def test_it_is_idempotent(tmp_path):
    one = tmp_path / "One.kuulas"
    seed(entry(1, str(one)), entry(2, "/else/Two.kuulas"))
    open_project(tmp_path).close()
    before = project_path(one).read_text(), default_path().read_text()
    again = open_project(tmp_path)
    try:
        assert ids(again.clipboard) == ["e0001"]
        assert ids(again.shared_clipboard) == ["e0002"]
    finally:
        again.close()
    assert (project_path(one).read_text(), default_path().read_text()) == before


def test_an_entry_already_in_the_project_is_not_duplicated(tmp_path):
    one = tmp_path / "One.kuulas"
    open_project(tmp_path).close()  # creates the project
    ClipboardStore(project_path(one)).update(lambda h: h.add(entry(1, str(one))))
    seed(entry(1, str(one)))  # the same id left behind in the shared file
    s = open_project(tmp_path)
    try:
        assert ids(s.clipboard) == ["e0001"]
        assert ids(s.shared_clipboard) == []
    finally:
        s.close()


def test_entries_keep_their_time_order_among_the_projects_own(tmp_path):
    one = tmp_path / "One.kuulas"
    open_project(tmp_path).close()
    ClipboardStore(project_path(one)).update(lambda h: (h.add(entry(2, str(one))),
                                                        h.add(entry(6, str(one)))))
    seed(entry(1, str(one)), entry(4, str(one)), entry(9, str(one)))
    s = open_project(tmp_path)
    try:
        assert ids(s.clipboard) == ["e0009", "e0006", "e0004", "e0002", "e0001"]
    finally:
        s.close()


def test_shared_copies_of_this_projects_entries_stay_shared(tmp_path):
    one = tmp_path / "One.kuulas"
    seed(entry(1, str(one), shared=True), entry(2, str(one)))
    s = open_project(tmp_path)
    try:
        assert ids(s.clipboard) == ["e0002"]
        assert ids(s.shared_clipboard) == ["e0001"]  # marked: it is the shared copy
    finally:
        s.close()


def test_the_same_folder_spelled_differently_is_the_same_project(tmp_path):
    one = tmp_path / "One.kuulas"
    one.mkdir()
    link = tmp_path / "link"
    link.symlink_to(tmp_path)
    seed(entry(1, str(link / "One.kuulas")),
         entry(2, str(tmp_path / "x" / ".." / "One.kuulas")))
    s = open_project(tmp_path)
    try:
        assert sorted(ids(s.clipboard)) == ["e0001", "e0002"]
        assert ids(s.shared_clipboard) == []
    finally:
        s.close()


def test_a_read_only_open_moves_nothing(tmp_path):
    first = open_project(tmp_path)
    (own,) = (first.package.path / "locks").glob("*.json")
    lock = json.loads(own.read_text())
    (first.package.path / "locks" / "other.json").write_text(json.dumps({
        **lock, "instance": "other", "host": socket.gethostname(), "pid": os.getppid()}))
    seed(entry(1, str(first.package.path)))
    second = open_project(tmp_path)
    try:
        assert second.read_only
        assert ids(second.shared_clipboard) == ["e0001"]
        assert not project_path(first.package.path).exists()
    finally:
        second.close()
        first.close()


def test_nothing_leaves_the_shared_file_when_the_project_cannot_be_written(
        tmp_path, monkeypatch):
    seed(entry(1, str(tmp_path / "One.kuulas")))
    real = ClipboardStore._write

    def boom(self, text):
        if self.path != default_path():
            raise OSError("disk full")
        return real(self, text)

    with monkeypatch.context() as patch:
        patch.setattr(ClipboardStore, "_write", boom)
        s = open_project(tmp_path)
        try:
            assert ids(s.shared_clipboard) == ["e0001"]  # still there: nothing lost
        finally:
            s.close()
    again = open_project(tmp_path)  # the next open tries again
    try:
        assert ids(again.clipboard) == ["e0001"]
        assert ids(again.shared_clipboard) == []
    finally:
        again.close()


def test_a_damaged_shared_file_does_not_stop_the_project_opening(tmp_path):
    default_path().parent.mkdir(parents=True, exist_ok=True)
    default_path().write_text("{broken", encoding="utf-8")
    s = open_project(tmp_path)
    try:
        assert ids(s.clipboard) == []
    finally:
        s.close()


def test_a_shared_file_that_cannot_be_written_back_keeps_the_project_copy(
        tmp_path, monkeypatch):
    seed(entry(1, str(tmp_path / "One.kuulas")))
    real = ClipboardStore._write

    def boom(self, text):
        if self.path == default_path():
            raise OSError("read-only file system")
        return real(self, text)

    with monkeypatch.context() as patch:
        patch.setattr(ClipboardStore, "_write", boom)
        s = open_project(tmp_path)
        try:
            assert ids(s.clipboard) == ["e0001"]  # copied first, so never lost
            assert ids(s.shared_clipboard) == ["e0001"]  # could not be removed yet
        finally:
            s.close()
    again = open_project(tmp_path)  # the leftover is cleaned up on the next open
    try:
        assert ids(again.clipboard) == ["e0001"]
        assert ids(again.shared_clipboard) == []
    finally:
        again.close()
