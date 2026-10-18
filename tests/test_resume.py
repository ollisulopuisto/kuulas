"""resume.json: where the user left off, travelling with the project (not state)."""

import json
import time

from kuulas.resume import RESUME_NAME, ResumeWriter, read_resume
from kuulas.session import Session
from kuulas.syncmark import IGNORED
from kuulas.view_memory import ViewMemory

VIEW = {"playhead": 4800, "inPoint": 100, "outPoint": 900, "focusTrack": "t1",
        "zoom": 12.5, "scroll": 2400, "laneHeight": 60}


def test_remember_writes_the_resume_file(tmp_path):
    w = ResumeWriter(tmp_path)
    w.remember(VIEW)
    data = json.loads((tmp_path / RESUME_NAME).read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["saved_at"].endswith("Z")
    assert data["host"]
    keys = ("playhead", "in", "out", "focus_track", "zoom", "scroll")
    assert {k: data[k] for k in keys} == {
        "playhead": 4800, "in": 100, "out": 900, "focus_track": "t1", "zoom": 12.5,
        "scroll": 2400}
    assert "laneHeight" not in data


def test_no_temp_files_are_left_behind(tmp_path):
    ResumeWriter(tmp_path).remember(VIEW)
    assert [p.name for p in tmp_path.iterdir()] == [RESUME_NAME]


def test_writes_are_throttled_but_the_last_one_still_lands(tmp_path):
    w = ResumeWriter(tmp_path, interval=0.3)
    w.remember({**VIEW, "playhead": 1})
    w.remember({**VIEW, "playhead": 2})
    w.remember({**VIEW, "playhead": 3})
    assert read_resume(tmp_path)["playhead"] == 1  # the others wait
    deadline = time.monotonic() + 3
    while read_resume(tmp_path)["playhead"] != 3 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert read_resume(tmp_path)["playhead"] == 3
    w.close()


def test_close_writes_at_once(tmp_path):
    w = ResumeWriter(tmp_path, interval=60)
    w.remember({**VIEW, "playhead": 1})
    w.remember({**VIEW, "playhead": 2})
    w.close()
    assert read_resume(tmp_path)["playhead"] == 2


def test_close_with_a_position_replaces_the_playhead(tmp_path):
    w = ResumeWriter(tmp_path, interval=60)
    w.remember(VIEW)
    w.close(playhead=777)
    assert read_resume(tmp_path)["playhead"] == 777


def test_close_without_anything_remembered_writes_nothing(tmp_path):
    ResumeWriter(tmp_path).close(playhead=5)
    assert not (tmp_path / RESUME_NAME).exists()


def test_a_failure_is_logged_not_raised(tmp_path, caplog):
    w = ResumeWriter(tmp_path / "missing" / "folder")
    w.remember(VIEW)
    w.close()
    assert caplog.records


def test_disabled_writer_writes_nothing(tmp_path):
    w = ResumeWriter(tmp_path, enabled=False)
    w.remember(VIEW)
    w.close()
    assert not (tmp_path / RESUME_NAME).exists()


def test_junk_views_are_ignored(tmp_path):
    w = ResumeWriter(tmp_path)
    w.remember({"playhead": "x", "zoom": float("nan"), "inPoint": True})
    data = read_resume(tmp_path)
    assert not {"playhead", "zoom", "in"} & set(data)


def test_read_ignores_corrupt_and_foreign_files(tmp_path):
    (tmp_path / RESUME_NAME).write_text("{nope", encoding="utf-8")
    assert read_resume(tmp_path) is None
    (tmp_path / RESUME_NAME).write_text("[1]", encoding="utf-8")
    assert read_resume(tmp_path) is None
    (tmp_path / RESUME_NAME).write_text('{"playhead": 5}', encoding="utf-8")
    assert read_resume(tmp_path) is None  # no saved_at: cannot be ordered
    assert read_resume(tmp_path / "nowhere") is None


def test_a_conflicted_copy_is_never_read(tmp_path):
    name = "resume (Olli's MacBook's conflicted copy 2026-10-18).json"
    (tmp_path / name).write_text(
        json.dumps({"version": 1, "saved_at": "2026-10-18T10:00:00Z", "playhead": 9}),
        encoding="utf-8")
    assert read_resume(tmp_path) is None


def test_the_session_writes_on_close_and_makes_no_history_step(tmp_path):
    folder = tmp_path / "Talk.kuulas"
    s = Session(folder)
    head = s.history.head
    s.resume.remember(VIEW)
    assert s.history.head == head  # not project state: no step, no undo
    s.close()
    assert read_resume(folder)["playhead"] == 4800


def test_flush_view_saves_the_given_position_to_both_places(tmp_path):
    folder = tmp_path / "Talk.kuulas"
    s = Session(folder)
    manifest_id = s.package.manifest["id"]
    s.resume.remember({**VIEW, "playhead": 10})
    s.flush_view(playhead=999)
    assert read_resume(folder)["playhead"] == 999
    assert ViewMemory().get(manifest_id)["playhead"] == 999
    s.close()


def test_flush_view_with_nothing_remembered_changes_nothing(tmp_path):
    folder = tmp_path / "Talk.kuulas"
    s = Session(folder)
    s.flush_view(playhead=999)
    s.close()
    assert read_resume(folder) is None


def test_resume_json_is_never_marked_ignored_by_dropbox():
    assert RESUME_NAME not in IGNORED  # it must sync
