"""The stems kuulas gives the automixer (WP68): the folder route reads tracks.json
strictly (podcast repo, docs/KUULAS-INTEGRATION.md, "Status (2026-10-19)"), so
the export must satisfy these rules. Speech-mix tracks are left out of this
export, music is stereo, the project must be 48 kHz."""

import json
import threading
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import automix, export, messages
from kuulas.session import Session


class Reports:
    def __call__(self, *_args, **_kwargs):
        pass


def tone(path: Path, rate: int, seed: int, channels: int = 1) -> str:
    rng = np.random.default_rng(seed)
    audio = (rng.standard_normal((rate * 2, channels)) * 0.1).astype(np.float32)
    sf.write(path, audio, rate, subtype="PCM_16")
    return str(path)


def build(tmp_path, rate=48000):
    s = Session(tmp_path / "Episode.kuulas", rate=rate)
    src = tmp_path / "src"
    src.mkdir()
    s.import_media([tone(src / "Olli.wav", rate, 1), tone(src / "Maija.wav", rate, 2),
                    tone(src / "Theme.wav", rate, 3), tone(src / "Room.wav", rate, 4)])
    return s


@pytest.fixture
def session(tmp_path):
    s = build(tmp_path)
    tracks = s.state.tracks
    s.edit("set_track", {"track_id": tracks[2].id, "kind": "music", "name": "Theme"})
    s.edit("set_track", {"track_id": tracks[3].id, "kind": "speech-mix", "name": "Room"})
    yield s
    s.close()


def stems(session, tmp_path):
    """Export the way the automixer run does; returns (folder, tracks.json)."""
    out = tmp_path / "stems"
    done = automix.export_stems(session, out)
    folder = Path(done["path"])
    return folder, json.loads((folder / "tracks.json").read_text("utf-8"))


def test_manifest_satisfies_the_folder_routes_rules(session, tmp_path):
    folder, listing = stems(session, tmp_path)
    assert listing["version"] == 1
    assert listing["rate"] == 48000
    assert listing["start_frame"] == 0
    assert listing["processing"] == "dry"
    names = [t["name"] for t in listing["tracks"]]
    assert len(set(names)) == len(names)
    for track in listing["tracks"]:
        info = sf.info(folder / track["file"])
        assert info.frames == listing["frames"], track["name"]
        assert info.samplerate == 48000, track["name"]
        assert info.channels == track["channels"], track["name"]
        if track["kind"] == "music":
            assert track["channels"] == 2, "music must be stereo"
    assert automix.check_stems(folder) is None


def test_speech_mix_tracks_are_not_exported_but_speech_and_music_are(session, tmp_path):
    _folder, listing = stems(session, tmp_path)
    assert {t["kind"] for t in listing["tracks"]} == {"speech", "music"}
    assert [t["name"] for t in listing["tracks"]] == ["Olli", "Maija", "Theme"]


def test_a_mono_music_file_is_exported_as_stereo(session, tmp_path):
    _folder, listing = stems(session, tmp_path)
    music = next(t for t in listing["tracks"] if t["kind"] == "music")
    assert music["channels"] == 2


def test_the_normal_tracks_export_still_has_every_track(session, tmp_path):
    args = session.tracks_export_args({"folder": str(tmp_path / "n")})
    result = export.run(session, args)
    listing = json.loads((Path(result["path"]) / "tracks.json").read_text("utf-8"))
    assert {t["kind"] for t in listing["tracks"]} == {"speech", "speech-mix", "music"}
    assert len(listing["tracks"]) == 4


def test_a_muted_track_is_marked_not_audible(session, tmp_path):
    session.edit("set_track", {"track_id": session.state.tracks[1].id, "mute": True})
    _folder, listing = stems(session, tmp_path)
    assert {t["name"]: t["audible"] for t in listing["tracks"]}["Maija"] is False


@pytest.mark.parametrize(("field", "value"), [
    ("version", 2), ("rate", 44100), ("start_frame", 10), ("processing", "as_heard"),
    ("frames", 5)])
def test_check_stems_refuses_what_the_automixer_refuses(session, tmp_path, field, value):
    folder, listing = stems(session, tmp_path)
    listing[field] = value
    (folder / "tracks.json").write_text(json.dumps(listing), encoding="utf-8")
    with pytest.raises(automix.AutomixError) as e:
        automix.check_stems(folder)
    assert e.value.key == "error.automix.bad_stems"
    assert field in e.value.params["detail"]


def test_check_stems_refuses_speech_mix_and_mono_music(session, tmp_path):
    folder, listing = stems(session, tmp_path)
    listing["tracks"][0]["kind"] = "speech-mix"
    (folder / "tracks.json").write_text(json.dumps(listing), encoding="utf-8")
    with pytest.raises(automix.AutomixError):
        automix.check_stems(folder)
    listing["tracks"][0]["kind"] = "music"  # a mono file claimed to be music
    (folder / "tracks.json").write_text(json.dumps(listing), encoding="utf-8")
    with pytest.raises(automix.AutomixError):
        automix.check_stems(folder)


def test_a_project_not_at_48k_is_refused_before_anything_runs(tmp_path):
    s = build(tmp_path, rate=44100)
    ran = []

    def runner(*_a):
        ran.append(1)
        return 0

    try:
        with pytest.raises(automix.AutomixError) as e:
            automix.run(s, {}, {"command": ["x"]}, Reports(), threading.Event(),
                        run_process=runner)
        assert e.value.key == "error.automix.bad_rate"
        assert e.value.params["rate"] == 44100
        assert "44100" in str(messages.t(e.value.key, **e.value.params))
        with pytest.raises(automix.AutomixError):
            s.automix({})  # also refused when the job is queued
        assert ran == []
    finally:
        s.close()
