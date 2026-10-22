"""Readable History step names, made when the list is read (step_names.py)."""

import json
from pathlib import Path

import pytest

from kuulas import messages, ops, step_names
from kuulas.model import Clip, Project, Track

LOCALES = Path(__file__).resolve().parents[1] / "src" / "kuulas" / "locales"


@pytest.fixture(autouse=True)
def english():
    before = messages.language()
    messages.set_language("en")
    yield
    messages.set_language(before)


def project() -> Project:
    rate = Project().rate
    olli = Track(id="t1", name="Olli", clips=(
        Clip(id="c1", media="m", start=0, offset=0, length=rate * 10),))
    anna = Track(id="t2", name="Anna", clips=(
        Clip(id="c2", media="m", start=0, offset=0, length=rate * 10),))
    return Project(tracks=(olli, anna))


def name(op: str, args: dict, **kw) -> str:
    return step_names.describe({"name": op, "args": args}, project(), **kw)["name"]


def test_every_operation_has_a_readable_name():
    """Like the menu-coverage test: the list of ops without a name stays empty."""
    missing = [op for op in [*ops.OPS, "restore"] if op not in step_names.DESCRIBERS]
    assert missing == []


def test_every_name_has_its_text_in_english_and_finnish():
    en = json.loads((LOCALES / "en.json").read_text())
    fi = json.loads((LOCALES / "fi.json").read_text())
    keys = {k for k in en if k.startswith("history.op.")}
    assert {f"history.op.{op}" for op in step_names.DESCRIBERS} <= keys
    assert keys <= set(fi)


@pytest.mark.parametrize("op", sorted(step_names.DESCRIBERS))
def test_a_name_never_fails_on_missing_arguments(op):
    for lang in ("en", "fi"):
        messages.set_language(lang)
        out = step_names.describe({"name": op, "args": {}}, project())
        assert out["name"]
        assert "{" not in out["name"]
        assert "history.op" not in out["name"]


def test_track_settings_name_the_track_and_the_gain():
    assert name("set_track", {"track_id": "t1", "gain_db": -3.0}) == \
        "Track settings: Olli · gain \u22123.0 dB"


def test_split_names_the_track_and_the_time():
    rate = Project().rate
    assert name("split_clip", {"clip_id": "c2", "at": int(rate * 754.5)}) == \
        "Split: Anna at 12:34.5"


def test_a_deleted_track_falls_back_to_a_track():
    assert name("set_track", {"track_id": "gone"}) == "Track settings: a track"


def test_finnish_names():
    messages.set_language("fi")
    rate = Project().rate
    assert name("split_clip", {"clip_id": "c2", "at": int(rate * 754.5)}) == \
        "Jako: Anna kohdassa 12:34,5"


def test_a_restore_names_its_target():
    out = name("restore", {"node": "x"},
               target={"op": {"name": "set_track", "args": {"track_id": "t1"}},
                       "label": "set_track"})
    assert out == "Restored to: Track settings: Olli"


def test_an_op_with_no_describer_keeps_its_stored_label():
    out = step_names.describe({"name": "auto_silence", "args": {}}, project(),
                              label="Auto-silence")
    assert out["name"] == "Auto-silence"
    assert out["run"] is None


def test_steps_on_one_object_share_a_run_key():
    one = step_names.describe({"name": "set_track", "args": {"track_id": "t1"}},
                              project())
    two = step_names.describe({"name": "set_track", "args": {"track_id": "t1",
                                                             "gain_db": -9.0}}, project())
    other = step_names.describe({"name": "set_track", "args": {"track_id": "t2"}},
                                project())
    assert one["run"] == two["run"] != other["run"]
    assert two["base"] == "Track settings: Olli"
    assert two["detail"] == "gain \u22129.0 dB"
