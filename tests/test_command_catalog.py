"""The command catalogue (WP53): every edit and every session command, with its arguments
and a one-line summary, so a program (or an LLM) can find what kuulas can do without
knowing it in advance. A command with no entry is a failing test."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from test_server import FakeEngine

from kuulas import command_catalog, messages, ops
from kuulas.server import create_app
from kuulas.session import CLIPBOARD_EDITS, COMMANDS, Session


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


def by_name():
    return {entry["name"]: entry for entry in command_catalog.catalog()}


def pairs():
    return [(entry["via"], entry["name"]) for entry in command_catalog.catalog()]


def test_every_edit_and_session_command_has_an_entry():
    listed = set(pairs())
    for name in ops.OPS:
        assert ("/api/edit", name) in listed, f"edit {name} is not in the catalogue"
    for name in COMMANDS:
        assert ("/api/command", name) in listed, f"command {name} is not in the catalogue"
    for name in CLIPBOARD_EDITS:
        assert ("/api/edit", name) in listed, f"clipboard edit {name} is missing"


def test_the_catalogue_names_only_commands_that_exist():
    known = (
        {("/api/edit", name) for name in ops.OPS}
        | {("/api/edit", name) for name in CLIPBOARD_EDITS}
        | {("/api/command", name) for name in COMMANDS}
    )
    assert set(pairs()) <= known


def test_a_name_is_unique_for_its_route():
    # resync is both an edit and a session command: two routes, so the pair is unique.
    assert len(pairs()) == len(set(pairs()))


def test_every_entry_says_what_it_is_in_one_line():
    for entry in command_catalog.catalog():
        assert entry["summary"].strip(), f"{entry['name']} has no summary"
        assert "\n" not in entry["summary"], f"{entry['name']}: the summary is one line"


def test_every_entry_says_how_to_call_it_and_whether_it_makes_an_undo_step():
    for entry in command_catalog.catalog():
        assert entry["via"] in ("/api/edit", "/api/command"), entry["name"]
        assert isinstance(entry["undo_step"], bool), entry["name"]
        for arg in entry["args"]:
            assert arg["name"], entry["name"]
            assert isinstance(arg["required"], bool), (entry["name"], arg["name"])


def test_the_catalogue_is_plain_json():
    json.dumps(command_catalog.catalog())


def test_an_edit_lists_its_arguments_from_its_signature():
    add_track = by_name()["add_track"]
    assert add_track["via"] == "/api/edit"
    assert add_track["undo_step"] is True
    args = {arg["name"]: arg for arg in add_track["args"]}
    assert "p" not in args, "the project is not an argument"
    assert args["name"]["required"] is False
    assert args["name"]["default"] == "Track"
    assert args["track_id"]["default"] is None
    delete_track = {arg["name"]: arg for arg in by_name()["delete_track"]["args"]}
    assert delete_track["track_id"]["required"] is True


def test_an_edit_that_takes_any_field_says_so():
    set_track = by_name()["set_track"]
    assert any(arg.get("variadic") for arg in set_track["args"])


def test_a_session_command_lists_what_it_reads_and_what_it_changes():
    auto = by_name()["auto_silence"]
    assert auto["via"] == "/api/command"
    assert auto["undo_step"] is True
    assert by_name()["relink"]["undo_step"] is False
    put_back = {arg["name"]: arg for arg in by_name()["put_back"]["args"]}
    assert put_back["start"]["required"]
    assert put_back["end"]["required"]
    assert put_back["track_ids"]["required"] is False


@pytest.fixture
def client(tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    session = Session(tmp_path / "Cat.kuulas")
    with TestClient(create_app(session, FakeEngine(), language="en", ui_dir=ui)) as c:
        yield c
    session.close()


def test_the_route_serves_the_catalogue(client):
    response = client.get("/api/commands")
    assert response.status_code == 200
    body = response.json()
    assert body["commands"] == json.loads(json.dumps(command_catalog.catalog()))
    assert {"/api/edit", "/api/command"} <= set(body["calls"])
