from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import messages, ops
from kuulas.music_report import build_report
from kuulas.session import Session


def _make_wav(path: Path, seconds: float = 1.0, rate: int = 48000) -> Path:
    audio = np.zeros(int(seconds * rate), dtype=np.float32)
    sf.write(str(path), audio, rate)
    return path


def test_set_music_info_creates_undoable_step(tmp_path: Path):
    wav = _make_wav(tmp_path / "song.wav")
    s = Session(tmp_path / "proj.kuulas")
    p = s.import_media([str(wav)])
    media = p.media[0]

    # Verify initial state has probe music_info (empty or dict)
    orig_info = dict(media.extra.get("music_info") or {})

    # 1. Edit music info
    s.set_music_info(media.id, {"title": "Test Title", "artist": "Test Artist"})
    m = s.history.state.media_item(media.id)
    assert m.extra["music_info"]["title"] == "Test Title"
    assert m.extra["music_info"]["artist"] == "Test Artist"

    # Step label verification in history
    head_node = s.history._node(s.history.head)
    expected_label = messages.t("history.set_music_info", media_id=media.id)
    assert head_node["label"] == expected_label

    # 2. Undo restores original probe value
    assert s.undo() is not None
    m_undone = s.history.state.media_item(media.id)
    assert m_undone.extra.get("music_info", {}) == orig_info

    # 3. Redo restores edited value
    assert s.redo() is not None
    m_redone = s.history.state.media_item(media.id)
    assert m_redone.extra["music_info"]["title"] == "Test Title"
    assert m_redone.extra["music_info"]["artist"] == "Test Artist"


def test_set_music_info_merges_fields_and_clears_on_empty(tmp_path: Path):
    wav = _make_wav(tmp_path / "song.wav")
    s = Session(tmp_path / "proj.kuulas")
    p = s.import_media([str(wav)])
    media = p.media[0]

    s.set_music_info(media.id, {"title": "Title 1", "artist": "Artist 1"})
    s.set_music_info(media.id, {"composer": "Composer 1"})

    info = s.history.state.media_item(media.id).extra["music_info"]
    assert info["title"] == "Title 1"
    assert info["artist"] == "Artist 1"
    assert info["composer"] == "Composer 1"

    # Clearing title with empty string
    s.set_music_info(media.id, {"title": ""})
    info2 = s.history.state.media_item(media.id).extra["music_info"]
    assert "title" not in info2 or info2["title"] == ""
    assert info2.get("artist") == "Artist 1"
    assert info2.get("composer") == "Composer 1"


def test_command_dispatcher_set_music_info(tmp_path: Path):
    wav = _make_wav(tmp_path / "song.wav")
    s = Session(tmp_path / "proj.kuulas")
    p = s.import_media([str(wav)])
    media = p.media[0]

    s.command(
        "set_music_info", {"media": media.id, "fields": {"title": "Dispatched Title"}}
    )
    m = s.history.state.media_item(media.id)
    assert m.extra["music_info"]["title"] == "Dispatched Title"


def test_set_music_info_rejects_bad_key_and_unknown_media(tmp_path: Path):
    wav = _make_wav(tmp_path / "song.wav")
    s = Session(tmp_path / "proj.kuulas")
    p = s.import_media([str(wav)])
    media = p.media[0]

    with pytest.raises(ops.EditError) as exc_key:
        s.set_music_info(media.id, {"bad_key": "val"})
    assert exc_key.value.key == "error.edit.bad_music_key"

    with pytest.raises(ops.EditError) as exc_media:
        s.set_music_info("nonexistent_id", {"title": "val"})
    assert exc_media.value.key == "error.edit.no_media"


def test_music_report_reflects_edited_tags(tmp_path: Path):
    wav = _make_wav(tmp_path / "music.wav", seconds=2.0)
    s = Session(tmp_path / "proj.kuulas")
    p = s.import_media([str(wav)])
    media = p.media[0]

    # Add a music track with clip
    p = s.history.state
    p = ops.add_track(p, "Music", kind="music")
    track_id = p.tracks[-1].id
    p = ops.add_clip(p, track_id, media.id, start=0, length=48000, offset=0)
    s.history.commit("add music track", p)

    report_before = build_report(s.history.state, s.store)
    assert len(report_before) == 1
    assert report_before[0].title == ""

    # Edit music tags
    s.set_music_info(media.id, {"title": "Royalty Song", "artist": "Famous Artist"})
    report_after = build_report(s.history.state, s.store)
    assert len(report_after) == 1
    assert report_after[0].title == "Royalty Song"
    assert report_after[0].artist == "Famous Artist"


def test_step_label_in_finnish(tmp_path: Path):
    wav = _make_wav(tmp_path / "song.wav")
    s = Session(tmp_path / "proj.kuulas")
    p = s.import_media([str(wav)])
    media = p.media[0]

    try:
        messages.set_language("fi")
        s.set_music_info(media.id, {"title": "Suomi Kappale"})
        node = s.history._node(s.history.head)
        expected = messages.t("history.set_music_info", media_id=media.id)
        assert node["label"] == expected
        assert "Musiikkitietojen muokkaus" in expected or "musiikki" in expected.lower()
    finally:
        messages.set_language("en")


def test_backwards_compatibility_missing_music_info_in_material(tmp_path: Path):
    wav = _make_wav(tmp_path / "song.wav")
    s = Session(tmp_path / "proj.kuulas")
    p = s.import_media([str(wav)])
    media = p.media[0]

    # Delete music_info from material root manually to simulate legacy project
    root = s.history.material
    root.pop("music_info", None)
    s.history.set_material("strip music_info", root)

    state = s.history.state
    m = state.media_item(media.id)
    assert isinstance(m.extra.get("music_info", {}), dict)


def _tagged_wav(path: Path) -> Path:
    with sf.SoundFile(str(path), "w", samplerate=48000, channels=1, format="WAV") as f:
        f.title = "Probe title"
        f.artist = "Probe artist"
        f.write(np.zeros(48000, dtype=np.float32))
    return path


def test_an_empty_string_blanks_an_imported_tag_and_none_brings_it_back(tmp_path: Path):
    s = Session(tmp_path / "proj.kuulas")
    p = s.import_media([str(_tagged_wav(tmp_path / "tagged.wav"))])
    media = p.media[0]
    assert media.extra["music_info"]["title"] == "Probe title"  # the precondition

    s.set_music_info(media.id, {"title": ""})
    shown = s.history.state.media_item(media.id).extra["music_info"]
    assert shown["title"] == ""
    assert shown["artist"] == "Probe artist"

    s.set_music_info(media.id, {"title": None})
    back = s.history.state.media_item(media.id).extra["music_info"]
    assert back["title"] == "Probe title"
