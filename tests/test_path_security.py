"""Request-derived file names stay in their selected folders; media is untouched."""

import json
import os

import pytest
from fastapi.testclient import TestClient
from test_server import FakeEngine

from kuulas import new_project, package, record_take
from kuulas.ops import EditError
from kuulas.record_session import RecordSession
from kuulas.series_library import SeriesLibrary, SeriesLibraryError
from kuulas.server import create_app
from kuulas.session import Session


@pytest.mark.parametrize("name", ["C:escape", "show:stream", 'a"b', "a?b", "a*b",
                                  "a|b", "a<b", "a>b", "a\nb", "a\tb"])
def test_project_names_are_portable_single_components(name):
    with pytest.raises(EditError):
        new_project.folder_name(name)


def test_new_project_rejects_a_dangling_link_without_creating_its_target(tmp_path):
    outside = tmp_path / "outside"
    parent = tmp_path / "chosen"
    parent.mkdir()
    (parent / "Show.kuulas").symlink_to(outside, target_is_directory=True)
    with pytest.raises(EditError):
        new_project.project_path(str(parent), "Show")
    assert not outside.exists()


def test_selected_parent_is_canonicalized_before_a_project_is_created(tmp_path):
    parent = tmp_path / "chosen"
    parent.mkdir()
    link = tmp_path / "shortcut"
    link.symlink_to(parent, target_is_directory=True)
    assert new_project.project_path(str(link), "Show") == parent / "Show.kuulas"


@pytest.mark.parametrize("take", ["../outside", "/outside", "..\\outside", "C:outside",
                                  "Take 1\n", "", ".."])
def test_editor_plan_paths_reject_non_take_names(tmp_path, take):
    with pytest.raises(ValueError, match="recording file"):
        record_take.plan_path(tmp_path, take)


def test_editor_plan_does_not_read_or_remove_a_link_outside_recordings(tmp_path):
    folder = tmp_path / "recordings"
    folder.mkdir()
    outside = tmp_path / "outside.editor.json"
    original = json.dumps({"take": "Take 1", "at": 123, "track_name": "Olli"})
    outside.write_text(original)
    (folder / "Take 1.editor.json").symlink_to(outside)
    assert record_take.read_plan(folder, "Take 1") is None
    record_take.remove_plan(folder, "Take 1")
    assert outside.read_text() == original
    assert (folder / "Take 1.editor.json").is_symlink()


def test_import_endpoint_rejects_traversal_and_sidecar_links(tmp_path):
    session = Session(tmp_path / "Show.kuulas")
    recorder = RecordSession(session, watch=False)
    outside = session.package.path / "outside.take.json"
    outside.write_text('{"state":"stopped","segments":[]}')
    recorder.folder.mkdir(exist_ok=True)
    (recorder.folder / "Take 1.take.json").symlink_to(outside)
    before = outside.read_bytes()
    try:
        with TestClient(create_app(session, FakeEngine(), recorder=recorder)) as client:
            response = client.post("/api/record/import", json={"takes": ["../outside"]})
            assert response.status_code == 400
            response = client.post("/api/record/import", json={"takes": ["Take 1"]})
            assert response.status_code == 404
        assert outside.read_bytes() == before
    finally:
        recorder.close()
        session.close()


def test_series_id_rejects_a_trailing_newline(tmp_path):
    with pytest.raises(SeriesLibraryError):
        SeriesLibrary(tmp_path).load("01900000-0000-7000-8000-000000000000\n")


def test_series_files_are_not_read_through_links(tmp_path):
    folder = tmp_path / "series"
    folder.mkdir()
    sid = "01900000-0000-7000-8000-000000000000"
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({
        "format": "kuulas-series", "id": sid, "name": "Other"}))
    (folder / f"{sid}.json").symlink_to(outside)
    lib = SeriesLibrary(folder)
    assert lib.load(sid) is None
    assert lib.list() == []


def test_atomic_json_never_opens_a_preexisting_temp_link(tmp_path, monkeypatch):
    outside = tmp_path / "recorded-file.wav"
    outside.write_bytes(b"irreplaceable recording")
    target = tmp_path / "settings.json"
    monkeypatch.setattr(package.secrets, "token_hex", lambda _: "known")
    link = target.with_name(f"{target.name}.{os.getpid()}.known.tmp")
    link.symlink_to(outside)
    package.write_json_atomic(target, {"safe": True})
    assert outside.read_bytes() == b"irreplaceable recording"
    assert json.loads(target.read_text()) == {"safe": True}
    assert not target.is_symlink()


def test_atomic_json_cleans_up_only_its_own_temp_on_serialization_error(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text('{"old":true}')
    with pytest.raises(TypeError):
        package.write_json_atomic(target, {"unsupported": object()})
    assert target.read_text() == '{"old":true}'
    assert list(tmp_path.iterdir()) == [target]


def test_editor_plan_write_never_follows_a_preexisting_temp_link(tmp_path):
    outside = tmp_path / "recorded.wav"
    outside.write_bytes(b"recording stays")
    plan_path = tmp_path / "Take 1.editor.json"
    plan_path.with_name(plan_path.name + ".tmp").symlink_to(outside)
    plan = record_take.TakePlan("Take 1", at=0, track_id=None,
                                track_name="Voice", channel=1)
    record_take.write_plan(tmp_path, plan)
    assert outside.read_bytes() == b"recording stays"
    assert record_take.read_plan(tmp_path, "Take 1") == plan


@pytest.mark.parametrize("job_id", [
    "../outside", "..\\outside", "C:outside", "*", "[ab]"])
def test_background_job_paths_reject_traversal_and_glob_inputs(tmp_path, job_id):
    from kuulas import bgjobs  # noqa: PLC0415

    for path in (bgjobs.job_file, bgjobs.status_file, bgjobs.cancel_file,
                 bgjobs.marker_file):
        with pytest.raises(bgjobs.BackgroundJobError):
            path(tmp_path, job_id)
    with pytest.raises(bgjobs.BackgroundJobError):
        bgjobs.result_file(tmp_path, job_id, "m123")
    with pytest.raises(bgjobs.BackgroundJobError):
        bgjobs.remove_files(tmp_path, job_id)


def test_background_job_files_do_not_follow_external_links(tmp_path):
    from kuulas import bgjobs  # noqa: PLC0415

    jobs = tmp_path / "jobs"
    jobs.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"id":"j1"}')
    (jobs / "j1.json").symlink_to(outside)
    with pytest.raises(bgjobs.BackgroundJobError):
        bgjobs.job_file(tmp_path, "j1")
    assert bgjobs.job_ids(tmp_path) == []
    assert outside.read_text() == '{"id":"j1"}'
