"""Export file names lead with the project; the edit only when it is not the main one."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import export, export_names, messages
from kuulas.session import Session

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "05 diet woke litteroitu.kuulas")
    path = tmp_path / "Olli.wav"
    sf.write(path, (np.random.default_rng(1).standard_normal(RATE) * 0.1)
             .astype(np.float32), RATE, subtype="PCM_16")
    s.import_media([str(path)])
    yield s
    s.close()


def test_main_edit_is_the_project_name_in_either_language():
    assert export_names.title("Show", "main", "Pääeditio") == "Show"
    assert export_names.title("Show", "x1", "Pääeditio") == "Show"
    assert export_names.title("Show", "x2", "Main") == "Show"


def test_another_edit_is_added_after_the_project():
    assert export_names.title("Show", "x3", "Cut for radio") == "Show - Cut for radio"


def test_stamp_has_hyphens_in_the_time_and_no_colons():
    when = datetime(2026, 10, 20, 15, 33, 43, tzinfo=UTC)
    assert export_names.stamp(when) == "2026-10-20 15-33-43"


def test_only_built_in_templates_are_migrated():
    assert export_names.migrate_template("{edit} v{n}.{ext}") == "{title} v{n}.{ext}"
    assert export_names.migrate_template("{edit}_{n}.{ext}") == "{edit}_{n}.{ext}"


def test_disposition_keeps_the_real_name():
    d = export_names.disposition("Pääeditio x.srt")
    assert d.startswith('attachment; filename="P__editio x.srt"')
    assert "filename*=UTF-8''P%C3%A4%C3%A4editio%20x.srt" in d


def test_mix_export_leads_with_the_project(session, tmp_path):
    out = tmp_path / "out"
    r = export.run(session, {"kind": "mix", "folder": str(out)})
    assert Path(r["path"]).name == "05 diet woke litteroitu v1.wav"


def test_mix_export_of_another_edit_names_the_edit(session, tmp_path):
    h = session.history
    h.create_edit("Radio")
    row = h.edits()[-1]
    h.edit, h.head = row["id"], row["head"]
    r = export.run(session, {"kind": "mix", "folder": str(tmp_path / "o")})
    assert Path(r["path"]).name == "05 diet woke litteroitu - Radio v1.wav"


def test_default_mix_file_template_uses_title_and_a_hyphen_stamp(session):
    args = session.mix_export_args({})
    assert args["template"] == "{title} {stamp} v{n}.{ext}"
    r = export.run(session, {**args, "folder": str(session.package.path.parent / "o")})
    name = Path(r["path"]).name
    assert name.startswith("05 diet woke litteroitu 20")
    assert ":" not in name
    assert export_names.stamp(datetime.now(UTC)).split(" ")[0] in name


def test_a_custom_saved_template_is_untouched(session, tmp_path):
    out = tmp_path / "out"
    export.run(session, {"kind": "mix", "folder": str(out),
                         "template": "{edit}_{n}.{ext}"})
    r = export.run(session, {"kind": "mix", "folder": str(out), "bit_depth": 16})
    assert Path(r["path"]).name == "Main_2.wav"
    assert session.last_export_settings("mix")["template"] == "{edit}_{n}.{ext}"


def test_a_remembered_old_default_becomes_the_new_one(session, tmp_path):
    h = session.history
    h.set_meta_json("export", {"settings": {"mix": {"template": "{edit} v{n}.{ext}"}}})
    r = export.run(session, {"kind": "mix", "folder": str(tmp_path / "o")})
    assert Path(r["path"]).name == "05 diet woke litteroitu v1.wav"


def test_title_field_in_a_custom_template(session, tmp_path):
    r = export.run(session, {"kind": "mix", "folder": str(tmp_path / "o"),
                             "template": "{project}|{title}.{ext}"})
    assert Path(r["path"]).name == "05 diet woke litteroitu_05 diet woke litteroitu.wav"


def test_stems_folder_and_files_lead_with_the_project(session, tmp_path):
    r = export.run(session, {"kind": "tracks", "folder": str(tmp_path / "o")})
    folder = Path(r["path"])
    assert folder.name == "05 diet woke litteroitu tracks v1"
    assert all(p.name.startswith("05 diet woke litteroitu \N{EN DASH} ")
               for p in folder.glob("*.wav"))


def test_regions_lead_with_the_project(session, tmp_path):
    session.edit("add_marker", {"marker_id": "r1", "name": "Intro", "start": 0,
                                "end": RATE // 2, "kind": "region"})
    plan, _ = export.plan_regions(session, {"folder": str(tmp_path / "o")})
    assert plan[0][2] == "05 diet woke litteroitu - 01 Intro.wav"
