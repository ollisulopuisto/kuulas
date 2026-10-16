"""Series storage (WP41): one JSON file per person and interview, written
atomically, so two machines editing different items never clash and a sync
conflict touches one item."""

import json
import os
import threading

import pytest

from kuulas import messages, package
from kuulas.series import SeriesError, SeriesStore

A = "01932f4a-0000-7000-8000-00000000000a"
B = "01932f4a-0000-7000-8000-00000000000b"


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


def person(pid, name):
    return {"id": pid, "name": name, "aliases": [], "role": "", "notes": ""}


def leftovers(tmp_path):
    return [p for p in (tmp_path / "people").iterdir() if p.suffix == ".tmp"]


def test_items_are_one_file_each_under_their_kind(tmp_path):
    s = SeriesStore(tmp_path / "Series")
    s.put("people", person(A, "Anna"))
    s.put("interviews", {"id": B, "title": "Talk"})
    assert (tmp_path / "Series" / "people" / f"{A}.json").is_file()
    assert (tmp_path / "Series" / "interviews" / f"{B}.json").is_file()
    assert s.get("people", A)["name"] == "Anna"
    assert [i["name"] for i in s.items("people")] == ["Anna"]
    s.delete("people", A)
    assert s.items("people") == []
    assert s.get("people", A) is None


def test_unknown_keys_and_unicode_round_trip(tmp_path):
    s = SeriesStore(tmp_path)
    item = {**person(A, "Jääskeläinen"), "future": {"x": [1, 2]}}
    s.put("people", item)
    assert SeriesStore(tmp_path).get("people", A) == item


def test_two_writers_editing_different_items_both_survive(tmp_path):
    one, two = SeriesStore(tmp_path), SeriesStore(tmp_path)  # two machines
    errors = []

    def write(store, pid, name):
        try:
            for i in range(20):
                store.put("people", person(pid, f"{name}{i}"))
        except Exception as e:  # noqa: BLE001 - collected so the test fails with the cause
            errors.append(e)

    threads = [threading.Thread(target=write, args=(one, A, "Anna")),
               threading.Thread(target=write, args=(two, B, "Ville"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    names = {i["id"]: i["name"] for i in one.items("people")}
    assert names == {A: "Anna19", B: "Ville19"}
    assert one.conflicts() == []
    assert leftovers(tmp_path) == []


def test_a_crash_while_writing_leaves_the_old_item(tmp_path, monkeypatch):
    s = SeriesStore(tmp_path)
    s.put("people", person(A, "Anna"))

    def crash(*_a):
        raise OSError("power cut")

    monkeypatch.setattr(package.os, "replace", crash)
    with pytest.raises(OSError, match="power cut"):
        s.put("people", person(A, "Changed"))
    monkeypatch.undo()
    assert s.get("people", A)["name"] == "Anna"
    assert leftovers(tmp_path) == []


@pytest.mark.parametrize("suffix", [
    " (Olli's conflicted copy 2026-10-16)",        # Dropbox
    ".sync-conflict-20261016-120000-ABCDEFG",      # Syncthing
    " 2",                                          # iCloud
    "-MacBook",                                    # OneDrive
])
def test_a_conflicted_copy_is_reported_and_not_taken_for_an_item(tmp_path, suffix):
    s = SeriesStore(tmp_path)
    s.put("people", person(A, "Anna"))
    copy = tmp_path / "people" / f"{A}{suffix}.json"
    copy.write_text(json.dumps(person(A, "Anna from the laptop")))
    [c] = s.conflicts()
    assert (c.kind, c.item_id, c.path, c.reason) == ("people", A, copy, "conflict")
    assert c.original_exists
    assert not c.identical
    assert A in str(c)
    # The canonical item is still the one read; the copy is not an item.
    assert [i["name"] for i in s.items("people")] == ["Anna"]


def test_a_conflicted_copy_identical_to_the_item_says_so(tmp_path):
    s = SeriesStore(tmp_path)
    s.put("people", person(A, "Anna"))
    (tmp_path / "people" / f"{A} (conflicted copy).json").write_text(
        json.dumps(person(A, "Anna")))
    assert s.conflicts()[0].identical


def test_a_conflict_whose_original_is_gone_is_reported_as_such(tmp_path):
    s = SeriesStore(tmp_path)
    (tmp_path / "people").mkdir(parents=True)
    (tmp_path / "people" / f"{A} (conflicted copy).json").write_text("{}")
    [c] = s.conflicts()
    assert not c.original_exists


def test_an_unreadable_item_is_reported_and_skipped(tmp_path):
    s = SeriesStore(tmp_path)
    s.put("people", person(B, "Ville"))
    (tmp_path / "people" / f"{A}.json").write_text("{not json")
    assert [i["id"] for i in s.items("people")] == [B]
    [c] = s.conflicts()
    assert (c.item_id, c.reason) == (A, "unreadable")


def test_an_item_whose_id_does_not_match_its_file_is_reported(tmp_path):
    s = SeriesStore(tmp_path)
    (tmp_path / "people").mkdir(parents=True)
    (tmp_path / "people" / f"{A}.json").write_text(json.dumps(person(B, "Ville")))
    assert s.items("people") == []
    assert s.conflicts()[0].reason == "mismatched"


def test_a_bad_kind_or_id_is_refused(tmp_path):
    s = SeriesStore(tmp_path)
    with pytest.raises(SeriesError) as err:
        s.put("bits", person(A, "x"))
    assert err.value.key == "error.series.bad_kind"
    for bad in ("../escape", "a/b", ""):
        with pytest.raises(SeriesError) as err:
            s.put("people", person(bad, "x"))
        assert err.value.key == "error.series.bad_id"
    assert not os.path.exists(tmp_path.parent / "escape.json")
