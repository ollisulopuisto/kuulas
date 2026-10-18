"""The per-user view memory (WP35): atomic, bounded, never fatal."""

import json
import logging

import pytest

from kuulas import view_memory
from kuulas.view_memory import MAX_PROJECTS, ViewMemory, ViewMemoryError


def test_a_missing_file_remembers_nothing(tmp_path):
    assert ViewMemory(tmp_path / "v.json").get("p1") is None


def test_a_view_survives_a_restart(tmp_path):
    path = tmp_path / "sub" / "v.json"
    ViewMemory(path).put("p1", {"zoom": 12.5, "scroll": 4800})
    assert ViewMemory(path).get("p1") == {"zoom": 12.5, "scroll": 4800}
    assert ViewMemory(path).get("p2") is None


def test_unknown_keys_are_kept(tmp_path):
    path = tmp_path / "v.json"
    ViewMemory(path).put("p1", {"zoom": 1, "from_the_future": {"a": [1, 2]}})
    assert ViewMemory(path).get("p1")["from_the_future"] == {"a": [1, 2]}


def test_unknown_top_level_keys_are_kept_on_write(tmp_path):
    path = tmp_path / "v.json"
    seed = {"version": 1, "projects": {}, "other": 7}
    path.write_text(json.dumps(seed), encoding="utf-8")
    ViewMemory(path).put("p1", {"zoom": 1})
    assert json.loads(path.read_text(encoding="utf-8"))["other"] == 7


@pytest.mark.parametrize("text", ["", "{not json", "[]", '{"projects": 5}',
                                  '{"projects": {"p1": 3}}', "\x00\x01"])
def test_a_damaged_file_means_no_memory(tmp_path, text, caplog):
    path = tmp_path / "v.json"
    path.write_text(text, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert ViewMemory(path).get("p1") is None
    if text:
        assert caplog.records


def test_a_damaged_file_is_replaced_by_the_next_write(tmp_path):
    path = tmp_path / "v.json"
    path.write_text("{not json", encoding="utf-8")
    ViewMemory(path).put("p1", {"zoom": 2})
    assert ViewMemory(path).get("p1") == {"zoom": 2}


def test_the_oldest_projects_are_dropped(tmp_path):
    memory = ViewMemory(tmp_path / "v.json")
    for n in range(MAX_PROJECTS + 5):
        memory.put(f"p{n}", {"zoom": n})
    assert memory.get("p0") is None
    assert memory.get("p4") is None
    assert memory.get("p5") == {"zoom": 5}
    assert memory.get(f"p{MAX_PROJECTS + 4}") == {"zoom": MAX_PROJECTS + 4}


def test_writing_a_project_again_makes_it_the_newest(tmp_path):
    memory = ViewMemory(tmp_path / "v.json")
    for n in range(MAX_PROJECTS):
        memory.put(f"p{n}", {"zoom": n})
    memory.put("p0", {"zoom": 99})
    memory.put("new", {"zoom": 1})
    assert memory.get("p0") == {"zoom": 99}
    assert memory.get("p1") is None


@pytest.mark.parametrize("bad", [[], "x", 3, None, {"a": "x" * 40_000}])
def test_junk_is_refused(tmp_path, bad):
    with pytest.raises(ViewMemoryError):
        ViewMemory(tmp_path / "v.json").put("p1", bad)


@pytest.mark.parametrize("project_id", ["", "x" * 300, 5, None])
def test_a_bad_project_id_is_refused(tmp_path, project_id):
    with pytest.raises(ViewMemoryError):
        ViewMemory(tmp_path / "v.json").put(project_id, {"zoom": 1})


def test_the_default_path_honours_the_override(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_VIEW_MEMORY_FILE", str(tmp_path / "x.json"))
    assert view_memory.default_path() == tmp_path / "x.json"


def test_a_failed_write_leaves_the_old_file(tmp_path, monkeypatch):
    path = tmp_path / "v.json"
    memory = ViewMemory(path)
    memory.put("p1", {"zoom": 1})

    def boom(*_a, **_k):
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(view_memory.os, "replace", boom)
        with pytest.raises(OSError, match="disk full"):
            memory.put("p1", {"zoom": 2})
    assert ViewMemory(path).get("p1") == {"zoom": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["v.json"]
