"""The per-user clipboard file (WP46 wiring): atomic, shared, never fatal."""

import json
import logging
from pathlib import Path

import pytest

from kuulas import clipboard_store
from kuulas.clipboard import ClipboardHistory, ClipRef, Entry
from kuulas.clipboard_store import MAX_ENTRIES, ClipboardStore
from kuulas.desktop import config_dir


def entry(n: int, pinned: bool = False) -> Entry:
    return Entry(f"e{n}", f"name {n}", float(n),
                 refs=(ClipRef("a" * 64, 0, 100),), span=(0, 100), pinned=pinned)


def test_a_missing_file_is_an_empty_history(tmp_path):
    assert ClipboardStore(tmp_path / "clipboard.json").load().entries() == ()


def test_entries_survive_a_restart(tmp_path):
    path = tmp_path / "sub" / "clipboard.json"
    ClipboardStore(path).update(lambda h: h.add(entry(1)))
    again = ClipboardStore(path).load()
    assert [e.id for e in again.entries()] == ["e1"]
    assert again.get("e1").refs[0].media_sha256 == "a" * 64


@pytest.mark.parametrize("text", ["", "{not json", "[]", '{"entries": 5}',
                                  '{"entries": [{"refs": [{}]}]}', "\x00\x01"])
def test_a_damaged_file_is_an_empty_history(tmp_path, text, caplog):
    path = tmp_path / "clipboard.json"
    path.write_text(text, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert ClipboardStore(path).load().entries() == ()
    if text:
        assert caplog.records  # said, not silent


def test_a_damaged_file_is_replaced_by_the_next_write(tmp_path):
    path = tmp_path / "clipboard.json"
    path.write_text("{broken", encoding="utf-8")
    store = ClipboardStore(path)
    store.update(lambda h: h.add(entry(1)))
    assert [e.id for e in store.load().entries()] == ["e1"]


def test_the_limit_is_fifty_whatever_the_file_says(tmp_path):
    path = tmp_path / "clipboard.json"
    big = ClipboardHistory(10_000)
    for n in range(80):
        big.add(entry(n))
    path.write_text(big.to_json(), encoding="utf-8")
    store = ClipboardStore(path)
    loaded = store.load()
    assert loaded.max_entries == MAX_ENTRIES == 50
    store.update(lambda h: h.add(entry(999)))
    assert len(store.load().entries()) == 50


def test_pinned_entries_do_not_count_toward_the_fifty(tmp_path):
    store = ClipboardStore(tmp_path / "clipboard.json")
    store.update(lambda h: h.add(entry(0)))
    store.update(lambda h: h.pin("e0"))
    for n in range(1, 60):
        store.update(lambda h, n=n: h.add(entry(n)))
    ids = [e.id for e in store.load().entries()]
    assert len(ids) == 51
    assert "e0" in ids


def test_a_write_leaves_no_partial_file_and_valid_json(tmp_path):
    path = tmp_path / "clipboard.json"
    ClipboardStore(path).update(lambda h: h.add(entry(1)))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["clipboard.json"]
    assert json.loads(path.read_text(encoding="utf-8"))["entries"][0]["id"] == "e1"


def test_a_failed_write_keeps_the_old_file(tmp_path, monkeypatch):
    path = tmp_path / "clipboard.json"
    store = ClipboardStore(path)
    store.update(lambda h: h.add(entry(1)))

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(OSError, match="disk full"):
        store.update(lambda h: h.add(entry(2)))
    monkeypatch.undo()
    assert [e.id for e in store.load().entries()] == ["e1"]
    assert [p.name for p in tmp_path.iterdir()] == ["clipboard.json"]


def test_update_returns_what_the_function_returns(tmp_path):
    store = ClipboardStore(tmp_path / "c.json")
    assert store.update(lambda h: len(h.entries())) == 0


def test_two_stores_on_one_file_see_each_others_entries(tmp_path):
    a, b = ClipboardStore(tmp_path / "c.json"), ClipboardStore(tmp_path / "c.json")
    a.update(lambda h: h.add(entry(1)))
    b.update(lambda h: h.add(entry(2)))
    assert [e.id for e in a.load().entries()] == ["e2", "e1"]


def test_the_default_path_follows_the_environment(monkeypatch, tmp_path):
    target = tmp_path / "x.json"
    monkeypatch.setenv("KUULAS_CLIPBOARD_FILE", str(target))
    assert clipboard_store.default_path() == target


def test_the_default_path_is_in_the_config_dir(monkeypatch):
    monkeypatch.delenv("KUULAS_CLIPBOARD_FILE")
    assert clipboard_store.default_path() == config_dir() / "clipboard.json"
    assert isinstance(clipboard_store.default_path(), Path)


def test_another_window_s_write_changes_the_stamp_and_shows_in_a_fresh_load(tmp_path):
    path = tmp_path / "clipboard.json"
    mine, theirs = ClipboardStore(path), ClipboardStore(path)  # two windows
    assert mine.stamp() is None  # no file yet
    theirs.update(lambda h: h.add(entry(1)))
    first = mine.stamp()
    assert first is not None
    assert [e.id for e in mine.load().entries()] == ["e1"]
    theirs.update(lambda h: h.add(entry(2)))
    assert mine.stamp() != first
    assert [e.id for e in mine.load().entries()] == ["e2", "e1"]


def test_two_windows_writing_in_turn_lose_nothing(tmp_path):
    path = tmp_path / "clipboard.json"
    a, b = ClipboardStore(path), ClipboardStore(path)
    for n in range(4):
        (a if n % 2 == 0 else b).update(lambda h, n=n: h.add(entry(n)))
    assert [e.id for e in a.load().entries()] == ["e3", "e2", "e1", "e0"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["clipboard.json"]
