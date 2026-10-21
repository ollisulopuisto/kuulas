"""Remove from the recent list: the list is edited, a project folder never is."""

from __future__ import annotations

from kuulas import desktop, messages
from kuulas.recent_projects import (
    drop_missing,
    insert_record,
    remove_record,
    replace_path,
)


class _Webview:
    class FileDialog:
        FOLDER = "folder"
        SAVE = "save"


class _Window:
    def __init__(self):
        self.pages = []

    def set_title(self, title):
        pass

    def load_html(self, html):
        self.pages.append(html)

    def evaluate_js(self, script):
        pass


def _bridge(tmp_path):
    bridge = desktop.Bridge(_Webview, tmp_path / "recents.json")
    bridge._window = _Window()
    return bridge


def _listed(tmp_path, *names, gone=()):
    file = tmp_path / "recents.json"
    folders = []
    for name in names:
        folder = tmp_path / name
        folder.mkdir()
        (folder / "manifest.json").write_text("{}", encoding="utf-8")
        desktop.add_recent(file, str(folder))
        folders.append(folder)
    for name in gone:
        desktop.add_recent(file, str(tmp_path / name))
    return file, folders


def _paths(file):
    return [r["path"] for r in desktop.load_recent_records(file)]


# -- pure list functions ---------------------------------------------------------


def test_remove_record_drops_every_spelling_and_keeps_the_rest():
    records = [{"path": "/a/A.kuulas"}, {"path": "/b/B.kuulas"}]
    assert remove_record(records, "/a/./A.kuulas/") == [{"path": "/b/B.kuulas"}]
    assert remove_record(records, "/zzz") == records
    assert len(records) == 2


def test_drop_missing_keeps_what_exists():
    records = [{"path": "/a"}, {"path": "/b"}]
    assert drop_missing(records, lambda p: p == "/b") == [{"path": "/b"}]


def test_insert_record_clamps_the_index_and_does_not_duplicate():
    records = [{"path": "/a"}, {"path": "/b"}]
    new = {"path": "/c"}
    assert [r["path"] for r in insert_record(records, new, 1, 20)] == ["/a", "/c", "/b"]
    assert [r["path"] for r in insert_record(records, new, 99, 20)] == ["/a", "/b", "/c"]
    again = insert_record(records, {"path": "/b"}, 0, 20)
    assert [r["path"] for r in again] == ["/b", "/a"]


def test_replace_path_keeps_place_and_facts():
    records = [{"path": "/a", "tracks": 3}, {"path": "/b"}]
    moved = replace_path(records, "/a", "/new")
    assert moved == [{"path": "/new", "tracks": 3}, {"path": "/b"}]
    assert replace_path(records, "/zz", "/new") == records


# -- the start page ----------------------------------------------------------------


def test_launcher_page_has_remove_tidy_and_the_translated_labels():
    for lang, word in (("en", "Remove from list"), ("fi", "Poista listalta")):
        messages.set_language(lang)
        try:
            page = desktop.launcher_html([{"path": "/x/Gone.kuulas", "exists": False}])
        finally:
            messages.set_language("en")
        assert word in page
        assert 'id="tidy"' in page
        assert "createOpener" in page
        assert "desktop.launcher" not in page
        assert "prefers-reduced-motion" in page


# -- the bridge ------------------------------------------------------------------


def test_remove_recent_drops_only_that_entry_and_leaves_the_folder(tmp_path):
    file, (a, b) = _listed(tmp_path, "A.kuulas", "B.kuulas")
    assert _bridge(tmp_path).remove_recent(str(a)) is True
    assert _paths(file) == [str(b.resolve())]
    assert (a / "manifest.json").is_file()


def test_remove_recent_is_idempotent_and_tolerates_a_missing_or_damaged_file(tmp_path):
    bridge = _bridge(tmp_path)
    assert bridge.remove_recent("/nowhere/X.kuulas") is False
    (tmp_path / "recents.json").write_text("{not json", encoding="utf-8")
    assert bridge.remove_recent("/nowhere/X.kuulas") is False
    file, (a,) = _listed(tmp_path, "A.kuulas")
    assert bridge.remove_recent(str(a)) is True
    assert bridge.remove_recent(str(a)) is False
    assert _paths(file) == []


def test_remove_recent_rejects_a_non_path(tmp_path):
    bridge = _bridge(tmp_path)
    assert bridge.remove_recent(None) is False
    assert bridge.remove_recent("") is False


def test_remove_missing_recents_removes_only_gone_entries(tmp_path):
    file, (a,) = _listed(tmp_path, "A.kuulas", gone=("Gone1.kuulas", "Gone2.kuulas"))
    bridge = _bridge(tmp_path)
    assert bridge.remove_missing_recents() == 2
    assert _paths(file) == [str(a.resolve())]
    assert bridge.remove_missing_recents() == 0
    assert a.is_dir()


def test_restore_recent_puts_the_record_back_at_its_place(tmp_path):
    file, _ = _listed(tmp_path, "A.kuulas", "B.kuulas")
    bridge = _bridge(tmp_path)
    records = desktop.load_recent_records(file)
    removed = records[1]
    assert bridge.remove_recent(removed["path"]) is True
    assert bridge.restore_recent(removed, 1) is True
    assert _paths(file) == [r["path"] for r in records]
    assert bridge.restore_recent(removed, 1) is True  # no duplicate
    assert _paths(file) == [r["path"] for r in records]
    assert bridge.restore_recent({"nope": 1}, 0) is False


def test_locate_recent_points_the_entry_at_the_chosen_folder(tmp_path):
    file, _ = _listed(tmp_path, "A.kuulas", gone=("Moved.kuulas",))
    moved_to = tmp_path / "new" / "Moved.kuulas"
    moved_to.mkdir(parents=True)
    (moved_to / "manifest.json").write_text("{}", encoding="utf-8")
    bridge = _bridge(tmp_path)
    old = str((tmp_path / "Moved.kuulas").resolve())
    bridge._dialog = lambda kind, **o: [str(moved_to)]
    assert bridge.locate_recent(old) is True
    assert str(moved_to.resolve()) in _paths(file)
    assert old not in _paths(file)
    assert len(bridge._window.pages) == 1  # the start page is redrawn


def test_locate_recent_refuses_a_folder_that_is_not_a_project(tmp_path):
    file, _ = _listed(tmp_path, gone=("Moved.kuulas",))
    plain = tmp_path / "plain"
    plain.mkdir()
    bridge = _bridge(tmp_path)
    old = str((tmp_path / "Moved.kuulas").resolve())
    bridge._dialog = lambda kind, **o: [str(plain)]
    assert bridge.locate_recent(old) is False
    bridge._dialog = lambda kind, **o: []
    assert bridge.locate_recent(old) is False
    assert _paths(file) == [old]
