"""People, interviews and who speaks (WP41): the data model and its commands."""

import json
import sqlite3

import numpy as np
import pytest
import soundfile as sf

from kuulas import db as dbm
from kuulas import messages, package, people, series
from kuulas.clock import FLICKS
from kuulas.history import History
from kuulas.ops import EditError
from kuulas.session import COMMANDS, Session

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Talk.kuulas")
    yield s
    s.close()


def wav(path, seconds=3.0, seed=0):
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32),
             RATE, subtype="PCM_16")
    return path


def words(*spans):
    """(text, start s, end s, speaker label) -> stored words."""
    return [{"w": w, "s": round(s * FLICKS), "e": round(e * FLICKS), "spk": spk}
            for w, s, e, spk in spans]


def three_files(tmp_path):
    return [str(wav(tmp_path / f"{n}.wav", seed=i))
            for i, n in enumerate(("anna", "ville", "zoom"), 1)]


def raw(session, media_id):
    h = session.history
    return h.transcript(h.transcript_rev(media_id))


# -- people and interviews are material -----------------------------------------


def test_a_new_project_has_no_people_or_interviews(session):
    assert session.people() == []
    assert session.interviews() == []


def test_create_and_edit_a_person_are_undoable_material_steps(session):
    pid = session.create_person("Anna Virtanen", role="host", aliases=["Anna V."])
    assert [p.name for p in session.people()] == ["Anna Virtanen"]
    assert session.person(pid).role == "host"
    assert session.person(pid).aliases == ("Anna V.",)
    session.edit_person(pid, name="Anna Korhonen", notes="married")
    assert session.person(pid).name == "Anna Korhonen"
    assert session.person(pid).notes == "married"
    assert session.person(pid).role == "host"  # untouched fields stay
    nodes = session.history.nodes()
    assert all(n["material_to"] is not None for n in nodes[-2:])
    session.undo()
    assert session.person(pid).name == "Anna Virtanen"
    session.undo()
    assert session.people() == []
    session.redo()
    session.redo()
    assert session.person(pid).name == "Anna Korhonen"


def test_people_survive_reopening(tmp_path):
    s = Session(tmp_path / "A.kuulas")
    pid = s.create_person("Ville")
    s.close()
    s = Session(tmp_path / "A.kuulas")
    assert s.person(pid).name == "Ville"
    s.close()


def test_a_person_needs_a_name(session):
    with pytest.raises(EditError) as err:
        session.create_person("  ")
    assert err.value.key == "error.people.empty_name"
    assert session.people() == []


def test_editing_an_unknown_person_changes_nothing(session):
    before = session.history.head
    with pytest.raises(EditError) as err:
        session.edit_person("nope", name="x")
    assert err.value.key == "error.people.no_person"
    assert session.history.head == before


def test_unknown_keys_on_people_and_interviews_round_trip():
    raw_person = {"id": "p1", "name": "A", "aliases": [], "role": "", "notes": "",
                  "from_the_future": {"x": 1}}
    assert people.Person.from_dict(raw_person).to_dict() == raw_person
    raw_iv = {"id": "i1", "title": "T", "date": "2026-10-16", "place": "",
              "participants": [], "media": [], "sync_group": "", "notes": "",
              "tags": [], "colour": "teal"}
    assert people.Interview.from_dict(raw_iv).to_dict() == raw_iv


def test_commands_table_carries_the_people_commands(session):
    for name in ("create_person", "edit_person", "create_interview",
                 "edit_interview", "set_media_person", "map_speakers"):
        assert name in COMMANDS
    session.command("create_person", {"name": "Anna"})
    assert [p.name for p in session.people()] == ["Anna"]


# -- who speaks -----------------------------------------------------------------


def test_a_mic_files_words_carry_its_person(session, tmp_path):
    session.import_media(three_files(tmp_path)[:1])
    mid = session.state.media[0].id
    session.set_transcript(mid, words(("hello", 0.0, 0.4, ""), ("there", 0.5, 0.9, "")),
                           "t")
    anna = session.create_person("Anna")
    assert "person" not in session.transcripts()[mid][0]
    session.set_media_person(mid, anna)
    assert session.state.media_item(mid).person == anna
    assert [w["person"] for w in session.transcripts()[mid]] == [anna, anna]
    assert {w["person"] for w in session.timeline_words()} == {anna}
    # Nothing stored changed: the person is resolved when read.
    assert all("person" not in w for w in raw(session, mid))
    session.undo()
    assert session.state.media_item(mid).person == ""
    assert "person" not in session.transcripts()[mid][0]


def test_a_mixs_labels_map_to_people_and_remapping_changes_no_word_text(
        session, tmp_path):
    session.import_media(three_files(tmp_path)[2:])
    mid = session.state.media[0].id
    session.set_transcript(mid, words(("hi", 0.0, 0.3, "SPEAKER_00"),
                                      ("hello", 0.4, 0.8, "SPEAKER_01"),
                                      ("so", 0.9, 1.2, "SPEAKER_00")), "t")
    stored = raw(session, mid)
    anna, ville = session.create_person("Anna"), session.create_person("Ville")
    session.map_speakers(mid, {"SPEAKER_00": anna, "SPEAKER_01": ville})
    assert [w["person"] for w in session.transcripts()[mid]] == [anna, ville, anna]
    assert session.speaker_map(mid) == {"SPEAKER_00": anna, "SPEAKER_01": ville}
    # The map was wrong: swap it. Words keep text, times and labels.
    session.map_speakers(mid, {"SPEAKER_00": ville, "SPEAKER_01": anna})
    after = session.transcripts()[mid]
    assert [w["person"] for w in after] == [ville, anna, ville]
    assert [{k: v for k, v in w.items() if k != "person"} for w in after] == stored
    assert raw(session, mid) == stored
    session.undo()
    assert [w["person"] for w in session.transcripts()[mid]] == [anna, ville, anna]


def test_a_label_left_unmapped_has_no_person(session, tmp_path):
    session.import_media(three_files(tmp_path)[2:])
    mid = session.state.media[0].id
    session.set_transcript(mid, words(("a", 0.0, 0.3, "S0"), ("b", 0.4, 0.8, "S1")), "t")
    anna = session.create_person("Anna")
    session.map_speakers(mid, {"S0": anna})
    assert [w.get("person", "") for w in session.transcripts()[mid]] == [anna, ""]


def test_a_new_transcript_revision_starts_with_its_own_empty_map(session, tmp_path):
    session.import_media(three_files(tmp_path)[2:])
    mid = session.state.media[0].id
    ws = words(("a", 0.0, 0.3, "S0"))
    session.set_transcript(mid, ws, "t1")
    anna = session.create_person("Anna")
    session.map_speakers(mid, {"S0": anna})
    session.set_transcript(mid, ws, "t2")
    assert session.speaker_map(mid) == {}


def test_mapping_needs_a_transcript_and_known_people(session, tmp_path):
    session.import_media(three_files(tmp_path)[2:])
    mid = session.state.media[0].id
    anna = session.create_person("Anna")
    with pytest.raises(EditError) as err:
        session.map_speakers(mid, {"S0": anna})
    assert err.value.key == "error.people.no_transcript"
    session.set_transcript(mid, words(("a", 0.0, 0.3, "S0")), "t")
    with pytest.raises(EditError) as err:
        session.map_speakers(mid, {"S0": "ghost"})
    assert err.value.key == "error.people.no_person"
    with pytest.raises(EditError) as err:
        session.set_media_person(mid, "ghost")
    assert err.value.key == "error.people.no_person"
    with pytest.raises(EditError) as err:
        session.set_media_person("mnone", anna)
    assert err.value.key == "error.edit.no_media"


# -- interviews -----------------------------------------------------------------


def test_one_interview_links_three_files_from_different_recorders(session, tmp_path):
    session.import_media(three_files(tmp_path), interview=False)
    anna, ville = session.create_person("Anna"), session.create_person("Ville")
    media = session.state.media
    iid = session.create_interview(
        "Kitchen talk", date="2026-10-16", place="Helsinki",
        participants=[{"person": anna, "role": "host"},
                      {"person": ville, "role": "guest"}],
        media=[m.id for m in media])
    iv = session.interview(iid)
    assert iv.title == "Kitchen talk"
    assert sorted(iv.media) == sorted(m.sha256 for m in media)
    assert [p["person"] for p in iv.participants] == [anna, ville]
    assert session.interview_of(media[2].id).id == iid
    # The interview can be changed later, each change undoable.
    session.edit_interview(iid, title="Kitchen talk, take 2", tags=["pilot"])
    assert session.interview(iid).tags == ("pilot",)
    session.undo()
    assert session.interview(iid).title == "Kitchen talk"
    session.undo()
    assert session.interviews() == []


def test_an_interview_follows_the_sync_group_of_its_files(session, tmp_path):
    session.import_media(three_files(tmp_path)[:2], interview=False)
    group = session.state.sync_groups[0].id
    iid = session.create_interview("Duo", media=[m.id for m in session.state.media],
                                   sync_group=group)
    assert session.interview(iid).sync_group == group


def test_interview_with_unknown_media_or_person_is_refused(session):
    with pytest.raises(EditError) as err:
        session.create_interview("X", media=["mghost"])
    assert err.value.key == "error.edit.no_media"
    with pytest.raises(EditError) as err:
        session.create_interview("X", participants=[{"person": "ghost", "role": ""}])
    assert err.value.key == "error.people.no_person"
    assert session.interviews() == []


def test_import_offers_one_interview_for_files_imported_together(session, tmp_path):
    session.import_media(three_files(tmp_path))
    [iv] = session.interviews()
    assert sorted(iv.media) == sorted(m.sha256 for m in session.state.media)
    assert iv.sync_group == session.state.sync_groups[0].id
    assert session.last_import_interview == iv.id
    # One step: undoing the import takes the interview with it.
    session.undo()
    assert session.interviews() == []
    session.redo()
    assert len(session.interviews()) == 1


def test_import_interview_can_be_declined_or_forced(session, tmp_path):
    files = three_files(tmp_path)
    session.import_media(files[:2], interview=False)
    assert session.interviews() == []
    assert session.last_import_interview is None
    session.import_media(files[2:], interview=True, interview_title="Solo")
    [iv] = session.interviews()
    assert iv.title == "Solo"
    assert len(iv.media) == 1


def test_a_single_file_import_makes_no_interview_by_default(session, tmp_path):
    session.import_media(three_files(tmp_path)[:1])
    assert session.interviews() == []


# -- passages -------------------------------------------------------------------


def test_passages_of_a_person_across_the_project(session, tmp_path):
    session.import_media(three_files(tmp_path), interview=False)
    anna_mic, _ville_mic, zoom = (m.id for m in session.state.media)
    anna, ville = session.create_person("Anna"), session.create_person("Ville")
    session.set_transcript(anna_mic, words(("good", 1.0, 1.3, ""),
                                           ("morning", 1.4, 1.9, "")), "a")
    session.set_media_person(anna_mic, anna)
    session.set_transcript(zoom, words(
        ("hi", 0.0, 0.3, "S0"), ("welcome", 0.4, 0.9, "S1"),
        ("to", 1.0, 1.2, "S1"), ("you", 2.0, 2.2, "S0")), "z")
    session.map_speakers(zoom, {"S0": anna, "S1": ville})
    found = session.passages(anna)
    assert sorted((p.media, p.text) for p in found) == sorted([
        (zoom, "hi"), (anna_mic, "good morning"), (zoom, "you")])
    first = next(p for p in found if p.media == anna_mic)
    assert (first.start, first.end) == (round(1.0 * FLICKS), round(1.9 * FLICKS))
    assert (first.first_word, first.last_word) == (0, 1)
    assert first.person == anna
    assert [p.text for p in session.passages(ville)] == ["welcome to"]
    assert session.passages("nobody") == []
    # Recording ranges: the clock the media's sync group runs on (origin + time).
    group = session.state.sync_groups[0]
    origin = dict(group.members)[anna_mic]
    assert first.group == group.id
    assert first.recording_start == origin + first.start
    assert first.recording_end == origin + first.end


def test_a_passage_splits_when_the_speaker_changes_and_not_otherwise(session, tmp_path):
    session.import_media(three_files(tmp_path)[2:])
    mid = session.state.media[0].id
    session.set_transcript(mid, words(("a", 0, .1, "S0"), ("b", .2, .3, "S0"),
                                      ("c", .4, .5, "S1"), ("d", .6, .7, "S0")), "t")
    anna, ville = session.create_person("Anna"), session.create_person("Ville")
    session.map_speakers(mid, {"S0": anna, "S1": ville})
    assert [p.text for p in session.passages(anna)] == ["a b", "d"]


def build_project(folder, files, labels, person):
    s = Session(folder)
    s.import_media(files, interview=False)
    mid = s.state.media[0].id
    s.set_transcript(mid, words(*labels), "t")
    s.history.commit("map", s.state, material={
        **s.history.material,
        "speakers": {str(s.history.transcript_rev(mid)): {"S0": person}}})
    s.close()


def test_passages_span_the_projects_of_a_series(tmp_path):
    anna = "00000000-0000-7000-8000-000000000001"  # a series-level person id
    for n in (1, 2):
        wav(tmp_path / f"ep{n}.wav", seed=n)
        build_project(tmp_path / f"Ep{n}.kuulas", [str(tmp_path / f"ep{n}.wav")],
                      [(f"episode {n}", 0.0, 0.5, "S0")], anna)
    found = series.passages_in_projects(
        [tmp_path / "Ep1.kuulas", tmp_path / "Ep2.kuulas"], anna)
    assert [(p.project.name, p.text) for p in found] == [
        ("Ep1.kuulas", "episode 1"), ("Ep2.kuulas", "episode 2")]
    assert series.passages_in_projects([tmp_path / "Ep1.kuulas"], "nobody") == []


# -- format ---------------------------------------------------------------------


def downgrade_to_v1(folder):
    """What a project made before WP41 looks like: no people or interviews in any
    material root, manifest and schema at version 1."""
    db = sqlite3.connect(folder / "project.sqlite")
    for rev, root in db.execute("select id, root from material_revs").fetchall():
        data = dbm.get_blob(db, root)
        for key in ("people", "interviews", "media_person"):
            data.pop(key, None)
        data["from_the_future"] = {"keep": True}
        db.execute("update material_revs set root=? where id=?",
                   (dbm.put_blob(db, "material", data), rev))
    db.execute("update meta set value='1' where key='schema_version'")
    db.commit()
    db.close()
    m = json.loads((folder / "manifest.json").read_text())
    package.write_manifest(folder, {**m, "version": 1, "min_reader": 1,
                                    "manifest_extra": 7})


def test_the_format_version_rises_and_min_reader_does_not(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    m = package.read_manifest(pkg.path)
    pkg.close()
    assert (m["version"], m["min_reader"]) == (2, 1)


def test_migration_adds_empty_people_and_interviews_and_keeps_history(tmp_path):
    s = Session(tmp_path / "Old.kuulas")
    s.import_media(three_files(tmp_path)[:2], interview=False)
    mid = s.state.media[0].id
    s.set_transcript(mid, words(("a", 0, .1, "")), "t")
    steps = [n["id"] for n in s.history.nodes()]
    s.close()
    folder = tmp_path / "Old.kuulas"
    downgrade_to_v1(folder)

    pkg = package.open_package(folder)
    m = package.read_manifest(folder)
    assert (m["version"], m["min_reader"], m["manifest_extra"]) == (2, 1, 7)
    assert len(list((folder / "backups").glob("pre-migration-v1-*.sqlite"))) == 1
    h = pkg.history
    assert h.material["people"] == {}
    assert h.material["interviews"] == {}
    # Unknown keys in the material root survive; and old steps still undo.
    assert h.material["from_the_future"] == {"keep": True}
    assert [n["id"] for n in h.nodes()] == steps
    assert h.undo()
    assert h.transcript_rev(mid) is None
    assert h.material["people"] == {}
    pkg.close()
    db = sqlite3.connect(folder / "project.sqlite")
    assert dict(db.execute("select key, value from meta"))["schema_version"] == "3"
    db.close()


def test_a_newer_projects_people_survive_a_save_by_this_version(tmp_path):
    s = Session(tmp_path / "A.kuulas")
    pid = s.create_person("Anna")
    root = s.history.material
    root["people"][pid]["badge"] = "gold"  # a key a newer kuulas added
    s.history.commit("from the future", s.state, material=root)
    s.edit_person(pid, notes="x")
    s.close()
    h = History(tmp_path / "A.kuulas" / "project.sqlite", read_only=True)
    assert h.material["people"][pid]["badge"] == "gold"
    h.close()
