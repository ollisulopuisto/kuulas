"""The series library (docs/design/SERIES.md): one JSON file per series in the
per-user folder, atomic writes, unknown keys kept, damage never fatal."""

from __future__ import annotations

import json

import pytest

from kuulas import series_library
from kuulas.series_library import SeriesLibrary, SeriesLibraryError


def test_the_folder_is_the_env_override_or_the_user_config(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_SERIES_DIR", str(tmp_path / "s"))
    assert series_library.default_folder() == tmp_path / "s"
    monkeypatch.delenv("KUULAS_SERIES_DIR")
    assert series_library.default_folder().name == "series"


def test_create_save_load_round_trip(tmp_path):
    lib = SeriesLibrary(tmp_path)
    record = lib.create("  Vikasietotila  ", {"automix": {"speech_debleed": False}})
    assert record["name"] == "Vikasietotila"
    assert record["format"] == "kuulas-series"
    assert record["settings"]["automix"]["speech_debleed"] is False
    assert (tmp_path / f"{record['id']}.json").is_file()
    assert lib.load(record["id"]) == record
    assert [r["id"] for r in lib.list()] == [record["id"]]


def test_save_keeps_keys_a_newer_kuulas_wrote(tmp_path):
    lib = SeriesLibrary(tmp_path)
    record = lib.create("Show", {})
    path = tmp_path / f"{record['id']}.json"
    data = json.loads(path.read_text())
    data["future"] = {"x": 1}
    path.write_text(json.dumps(data))
    lib.update(record["id"], settings={"auto_silence": {"margin_db": 9}})
    again = json.loads(path.read_text())
    assert again["future"] == {"x": 1}
    assert again["settings"]["auto_silence"]["margin_db"] == 9.0


def test_missing_damaged_and_conflicted_files_are_not_series(tmp_path):
    lib = SeriesLibrary(tmp_path)
    good = lib.create("Show", {})
    sid = good["id"]
    (tmp_path / f"{sid} (Olli's conflicted copy).json").write_text("{}")
    bad = "01900000-0000-7000-8000-000000000000"
    (tmp_path / f"{bad}.json").write_text("not json")
    assert [r["id"] for r in lib.list()] == [sid]
    assert lib.load(bad) is None
    assert lib.load("01900000-0000-7000-8000-00000000ffff") is None
    assert SeriesLibrary(tmp_path / "nowhere").list() == []


def test_ids_and_names_are_checked(tmp_path):
    lib = SeriesLibrary(tmp_path)
    with pytest.raises(SeriesLibraryError):
        lib.load("../escape")
    with pytest.raises(SeriesLibraryError):
        lib.create("   ", {})
    with pytest.raises(SeriesLibraryError):
        lib.update("01900000-0000-7000-8000-00000000ffff", name="x")


def test_save_with_a_known_id_recreates_a_lost_file(tmp_path):
    lib = SeriesLibrary(tmp_path)
    sid = "01900000-0000-7000-8000-0000000000aa"
    record = lib.create("Show", {}, series_id=sid)
    assert record["id"] == sid
    assert lib.load(sid)["name"] == "Show"


def test_music_entries_and_media_paths_are_kept_as_given(tmp_path):
    lib = SeriesLibrary(tmp_path)
    record = lib.create("Show", {})
    entry = {"id": "e1", "name": "Intro", "created_utc": 1.0, "refs": [], "span": [0, 10]}
    lib.update(record["id"], music={"entries": [entry]},
               media={"ab" * 32: {"name": "intro.wav", "paths": ["/x/intro.wav"]}})
    again = lib.load(record["id"])
    assert again["music"]["entries"] == [entry]
    assert again["media"]["ab" * 32]["paths"] == ["/x/intro.wav"]
