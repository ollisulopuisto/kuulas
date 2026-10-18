"""Narration script, take import and export guard, session and API (WP43)."""

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import messages, mixer
from kuulas.clock import FLICKS
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


def wav(path, seconds):
    rng = np.random.default_rng(1)
    sf.write(path, (rng.standard_normal(int(seconds * RATE)) * 0.1).astype(np.float32),
             RATE, subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    s = Session(tmp_path / "Talk.kuulas")
    s.import_media([str(wav(src / "a.wav", 40))])
    s.take_path = wav(src / "take.wav", 9)
    yield s
    s.close()


class _NoEngine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


@pytest.fixture
def client(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, _NoEngine(), language="en", ui_dir=ui)) as c:
        yield c


def words(session, text):
    """Words one per second on the first media, from second 0."""
    media_id = session.state.media[0].id
    ws = [{"w": w, "s": i * FLICKS, "e": i * FLICKS + FLICKS // 2}
          for i, w in enumerate(text.split())]
    session.set_transcript(media_id, ws, "test")


def add(session, pid, start, text, length=None):
    args = {"track_id": session.state.tracks[0].id, "start": start, "text": text,
            "placeholder_id": pid}
    if length is not None:
        args["length"] = length
    session.edit("add_placeholder", args)


def test_script_is_in_timeline_order_with_text_and_times(session):
    add(session, "b", 75 * RATE, "second line of narration")
    add(session, "a", 5 * RATE, "first line", length=6 * RATE)
    items = session.narration_script()
    assert [i["id"] for i in items] == ["a", "b"]
    assert items[0]["text"] == "first line"
    assert items[0]["time"] == "0:05"
    assert items[1]["time"] == "1:15"
    assert items[0]["seconds"] == 6
    assert items[0]["estimated"] is False
    assert items[1]["estimated"] is True


def test_script_context_is_twenty_words_either_side(session):
    words(session, " ".join(f"w{i}" for i in range(40)))
    add(session, "a", 30 * RATE, "narration", length=2 * RATE)
    item = session.narration_script()[0]
    before = item["before"].split()
    assert before == [f"w{i}" for i in range(10, 30)]
    assert item["after"].split() == [f"w{i}" for i in range(32, 40)]


def test_script_without_a_transcript_has_no_context(session):
    add(session, "a", RATE, "line")
    item = session.narration_script()[0]
    assert item["before"] == ""
    assert item["after"] == ""


def test_script_text_and_markdown(session):
    add(session, "a", 5 * RATE, "first line", length=6 * RATE)
    txt = session.narration_script_text("txt")
    assert "0:05" in txt
    assert "first line" in txt
    assert "6 s" in txt
    md = session.narration_script_text("md")
    assert md.startswith("# ")
    assert "first line" in md


def test_script_bad_format_is_a_translated_error(session):
    with pytest.raises(messages.KuulasError) as e:
        session.narration_script_text("pdf")
    assert e.value.key == "error.narration_script.bad_format"


def test_get_narration_script_txt_and_md_are_attachments(client, session):
    add(session, "a", RATE, "Äiti sanoi")
    r = client.get("/api/narration-script", params={"format": "txt"})
    assert r.status_code == 200
    assert "Äiti sanoi" in r.text
    disposition = r.headers["content-disposition"]
    assert disposition == 'attachment; filename="narration-script.txt"'
    r = client.get("/api/narration-script", params={"format": "md"})
    disposition = r.headers["content-disposition"]
    assert disposition == 'attachment; filename="narration-script.md"'


def test_get_narration_script_bad_format_is_a_translated_400(client):
    r = client.get("/api/narration-script", params={"format": "pdf"})
    assert r.status_code == 400
    assert "pdf" in r.json()["error"]["text"]


# -- take ----------------------------------------------------------------------


def test_placeholder_take_imports_and_replaces_in_one_undo_step(session):
    add(session, "a", 10 * RATE, "line", length=4 * RATE)
    before = session.state
    nodes = len(session.history.nodes())
    session.command("placeholder_take", {"placeholder_id": "a",
                                         "path": str(session.take_path)})
    after = session.state
    assert after.placeholders == ()
    track = after.tracks[0]
    take = next(c for c in track.clips if c.start == 10 * RATE)
    assert take.length == 9 * RATE
    assert len(session.history.nodes()) == nodes + 1
    session.undo()
    assert session.state.placeholders == before.placeholders
    assert [c.media for c in session.state.tracks[0].clips] == [
        c.media for c in before.tracks[0].clips]


def test_placeholder_take_through_the_command_route(client, session):
    add(session, "a", 10 * RATE, "line", length=4 * RATE)
    r = client.post("/api/command", json={"name": "placeholder_take", "args": {
        "placeholder_id": "a", "path": str(session.take_path)}})
    assert r.status_code == 200
    assert session.state.placeholders == ()


def test_placeholder_take_upload_route(client, session):
    add(session, "a", 10 * RATE, "line", length=4 * RATE)
    with session.take_path.open("rb") as f:
        r = client.post("/api/placeholder-take", data={"placeholder_id": "a"},
                        files={"file": ("take.wav", f, "audio/wav")})
    assert r.status_code == 200
    assert "placeholders" not in r.json()["project"]
    assert any(c.length == 9 * RATE and c.start == 10 * RATE
               for c in session.state.tracks[0].clips)


def test_placeholder_take_with_a_bad_file_changes_nothing(session, tmp_path):
    add(session, "a", 10 * RATE, "line", length=4 * RATE)
    bad = tmp_path / "x.txt"
    bad.write_text("no")
    with pytest.raises(messages.KuulasError):
        session.command("placeholder_take", {"placeholder_id": "a", "path": str(bad)})
    assert len(session.state.placeholders) == 1


# -- mixer, usage, export ----------------------------------------------------------


def test_a_placeholder_plays_silence_and_changes_no_audio(session):
    plain = session.state
    add(session, "a", 5 * RATE, "line", length=4 * RATE)
    with_ph = session.state
    a = mixer.mix(plain, session.store, 0, 10 * RATE)
    b = mixer.mix(with_ph, session.store, 0, 10 * RATE)
    assert np.array_equal(a, b)


def test_export_reports_unrecorded_placeholders_in_range(session, tmp_path):
    add(session, "a", 5 * RATE, "line", length=4 * RATE)
    add(session, "b", 30 * RATE, "line", length=2 * RATE)
    out = session.export({"kind": "mix", "folder": str(tmp_path / "out"),
                          "range": [0, 10 * RATE]})
    assert out["placeholders_skipped"] == 1
    out = session.export({"kind": "mix", "folder": str(tmp_path / "out2")})
    assert out["placeholders_skipped"] == 2


def test_export_without_placeholders_reports_zero(session, tmp_path):
    out = session.export({"kind": "mix", "folder": str(tmp_path / "out")})
    assert out["placeholders_skipped"] == 0
