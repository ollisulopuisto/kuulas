"""Marking clipboard entries as worth sharing (WP65 step 4)."""

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas.clipboard import ClipRef, Entry
from kuulas.clipboard_store import ClipboardStore, default_path
from kuulas.ops import EditError
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


def wav(path, seed):
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(RATE * 2) * 0.1).astype(np.float32), RATE,
             subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    s.import_media([str(wav(tmp_path / "a.wav", 1))])
    yield s
    s.close()


def copy(s, name=""):
    clip = s.state.tracks[0].clips[0].id
    return s.clipboard_copy(clip_ids=[clip], name=name)["entry"]["id"]


def shared_ids(s):
    return [e.id for e in s.shared_clipboard.load().entries()]


def test_marking_copies_the_entry_to_the_shared_store_with_the_same_id(session):
    mine = copy(session, "Intro")
    other = copy(session)
    session.clipboard_share(mine, True)
    assert shared_ids(session) == [mine]
    shared = session.shared_clipboard.load().get(mine)
    assert shared.shared is True
    assert shared.name == "Intro"
    assert shared.source_project == str(session.package.path)
    assert session.clipboard.load().get(mine).shared is True  # both copies say so
    assert session.clipboard.load().get(other).shared is False
    assert default_path().is_file()


def test_the_list_says_which_entries_are_shared(session):
    mine = copy(session)
    session.clipboard_share(mine, True)
    assert session.clipboard_list()[0]["shared"] is True


def test_unmarking_takes_it_out_of_the_shared_store_and_keeps_the_own_entry(session):
    mine = copy(session)
    session.clipboard_share(mine, True)
    session.clipboard_share(mine, False)
    assert shared_ids(session) == []
    assert session.clipboard.load().get(mine).shared is False


def test_marking_twice_does_not_duplicate(session):
    mine = copy(session)
    session.clipboard_share(mine, True)
    session.clipboard_share(mine, True)
    assert shared_ids(session) == [mine]


def test_sharing_an_unknown_entry_is_an_error(session):
    with pytest.raises(EditError):
        session.clipboard_share("nope", True)


def test_sharing_is_not_project_state(session):
    mine = copy(session)
    nodes, state = len(session.history.nodes()), session.state
    session.clipboard_share(mine, True)
    assert len(session.history.nodes()) == nodes
    assert session.state == state


def test_renaming_and_deleting_follow_into_the_shared_copy(session):
    mine = copy(session)
    session.clipboard_share(mine, True)
    session.clipboard_rename(mine, "Better name")
    assert session.shared_clipboard.load().get(mine).name == "Better name"
    session.clipboard_delete(mine)
    assert shared_ids(session) == []


def test_clearing_old_entries_leaves_the_shared_copies_alone(session):
    first = copy(session)
    session.clipboard_share(first, True)
    for _ in range(3):
        copy(session)
    assert session.clipboard_clear_old(2) == 2
    assert first not in [e["id"] for e in session.clipboard_list()]
    assert shared_ids(session) == [first]  # shared on purpose: unshare it to drop it


def test_an_unmarked_entry_can_be_unshared_from_the_shared_list(tmp_path, session):
    mine = copy(session)
    session.clipboard_share(mine, True)
    other = Session(tmp_path / "Two.kuulas")  # another project sees it in Shared
    try:
        assert [e["id"] for e in other.clipboard_shared()] == [mine]
        other.clipboard_share(mine, False)  # and may take it out of Shared
        assert shared_ids(other) == []
    finally:
        other.close()
    # the origin's flag is stale until it next opens: it believes the shared store
    assert session.clipboard.load().get(mine).shared is True


def test_opening_a_project_clears_a_stale_shared_flag(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    s.import_media([str(wav(tmp_path / "a.wav", 1))])
    mine = copy(s)
    s.clipboard_share(mine, True)
    s.shared_clipboard.update(lambda h: h.remove([mine]))  # unshared elsewhere
    s.close()
    again = Session(tmp_path / "One.kuulas")
    try:
        assert again.clipboard.load().get(mine).shared is False
    finally:
        again.close()


def test_a_shared_flag_that_is_still_true_survives_reopening(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    s.import_media([str(wav(tmp_path / "a.wav", 1))])
    mine = copy(s)
    s.clipboard_share(mine, True)
    s.close()
    again = Session(tmp_path / "One.kuulas")
    try:
        assert again.clipboard.load().get(mine).shared is True
        assert shared_ids(again) == [mine]
    finally:
        again.close()


def test_the_shared_list_is_newest_first_and_includes_other_projects(session):
    store = ClipboardStore(default_path())
    store.update(lambda h: h.add(Entry("old", "Old", 1.0, refs=(ClipRef("a" * 64, 0, 9),),
                                       span=(0, 9), source_project="/else/Two.kuulas",
                                       shared=True)))
    mine = copy(session)
    session.clipboard_share(mine, True)
    names = [e["id"] for e in session.clipboard_shared()]
    assert names == [mine, "old"]


# -- the API -------------------------------------------------------------------


class _Engine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}

    def close(self):
        pass


@pytest.fixture
def client(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, _Engine(), language="en", ui_dir=ui)) as c:
        yield c


def test_api_share_and_list_shared(client, session):
    mine = copy(session, "Intro")
    r = client.post(f"/api/clipboard/{mine}/share", json={"shared": True})
    assert r.status_code == 200
    assert [e["id"] for e in r.json()["entries"]] == [mine]
    assert r.json()["entries"][0]["shared"] is True
    listed = client.get("/api/clipboard/shared").json()["entries"]
    assert [e["id"] for e in listed] == [mine]
    assert listed[0]["name"] == "Intro"
    r = client.post(f"/api/clipboard/{mine}/share", json={"shared": False})
    assert r.json()["entries"][0]["shared"] is False
    assert client.get("/api/clipboard/shared").json()["entries"] == []


def test_api_share_of_an_unknown_entry_is_a_404_or_400(client):
    r = client.post("/api/clipboard/nope/share", json={"shared": True})
    assert r.status_code in (400, 404)
    assert r.json()["error"]["key"] == "error.clipboard.no_entry"


def test_api_share_needs_the_flag(client, session):
    mine = copy(session)
    assert client.post(f"/api/clipboard/{mine}/share", json={}).status_code == 400
