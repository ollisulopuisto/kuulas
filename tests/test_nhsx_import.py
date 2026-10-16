import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from nhsx import read as read_nhsx

from kuulas.clock import FLICKS
from kuulas.messages import KuulasError
from kuulas.server import create_app
from kuulas.session import Session

FIXTURE = (Path(__file__).parents[2] / "podcast" / "packages" / "nhsx" /
           "tests" / "data" / "h-test A.nhsx")
RATE = 48_000


class Engine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


def write_audio(path: Path, seconds=20):
    rng = np.random.default_rng(91 + sum(path.name.encode()))
    sf.write(path, rng.uniform(-0.2, 0.2, seconds * RATE).astype(np.float32),
             RATE, subtype="PCM_16")


def test_import_real_nhsx_fixture_maps_regions_gains_and_fades(tmp_path):
    nhsx_path = tmp_path / "h-test A.nhsx"
    shutil.copy(FIXTURE, nhsx_path)
    audio = tmp_path / "h-test Files"
    audio.mkdir()
    parsed = read_nhsx(nhsx_path)
    for item in parsed.files:
        write_audio(audio / item.name)

    session = Session(tmp_path / "Imported.kuulas")
    try:
        session.command("import_nhsx", {"path": str(nhsx_path)})
        state = session.state
        assert len(state.media) == 11
        assert "<Session" in state.extra["nhsx"]["source_xml"]
        assert [track.name for track in state.tracks] == [
            "A1-A3", "A4", "A5", "A6", "A9-A10", "A11"]
        assert sum(len(track.clips) for track in state.tracks) == 11

        a10 = next(track for track in state.tracks if track.name == "A9-A10")
        gain_clip = next(clip for clip in a10.clips if session.store.meta(
            clip.media)["name"] == "A10_both_gain_clipgain.wav")
        assert gain_clip.start == round(102.601 * RATE)
        assert gain_clip.gain_db == 6
        assert next(track for track in state.tracks if track.name == "A11").gain_db == -6

        fade_clip = next(clip for track in state.tracks for clip in track.clips
                         if session.store.meta(clip.media)["name"] == "A8_fade_short.wav")
        assert fade_clip.fade_in == round(1.6 * RATE)
        assert "FadeIn" in fade_clip.extra["nhsx"]["source_xml"]
        plateau_clip = next(clip for track in state.tracks for clip in track.clips
                            if session.store.meta(clip.media)["name"] ==
                            "A7_fade_plateau.wav")
        assert len(plateau_clip.envelope) > 10
    finally:
        session.close()


def test_import_nhsx_keeps_word_times_on_the_source_file_clock(tmp_path):
    source = tmp_path / "speech.wav"
    write_audio(source)
    path = tmp_path / "words.nhsx"
    path.write_text(
        '<Session><AudioPool><File Id="1" Name="speech.wav" Path="speech.wav" '
        'VendorFile="x">'
        '<Transcription><p><w s="0.100" l="0.200" sp="A">hello</w></p>'
        '</Transcription></File></AudioPool><Tracks><Track Name="Voice" VendorTrack="y">'
        '<Region Ref="1" Start="1.000" Length="0.500" Offset="0.200" VendorRegion="z"/>'
        '</Track></Tracks></Session>', encoding="utf-8")

    session = Session(tmp_path / "Words.kuulas")
    try:
        session.command("import_nhsx", {"path": str(path)})
        media_id = session.state.media[0].id
        assert session.transcripts()[media_id] == [
            {"w": "hello", "s": round(0.1 * FLICKS),
             "e": round(0.3 * FLICKS), "spk": "A"}]
        assert "VendorFile" in session.state.media[0].extra.get("nhsx", {}).get(
            "source_xml", "")
        clip = session.state.tracks[0].clips[0]
        assert "VendorRegion" in clip.extra["nhsx"]["source_xml"]
        assert "VendorTrack" in session.state.tracks[0].extra["nhsx"]["source_xml"]
        assert "VendorRegion" in session.state.extra["nhsx"]["source_xml"]
    finally:
        session.close()


def test_import_nhsx_invalid_xml_is_translated_and_changes_nothing(tmp_path):
    path = tmp_path / "broken.nhsx"
    path.write_text("<Session>", encoding="utf-8")
    session = Session(tmp_path / "Broken.kuulas")
    try:
        with pytest.raises(KuulasError) as exc:
            session.command("import_nhsx", {"path": str(path)})
        assert exc.value.key == "error.import.nhsx_failed"
        assert not session.state.media
        assert not session.state.tracks
    finally:
        session.close()


def test_import_nhsx_missing_audio_is_reported_without_failing_the_project(tmp_path):
    path = tmp_path / "missing.nhsx"
    path.write_text(
        '<Session><AudioPool><File Id="1" Name="gone.wav" Path="gone.wav"/>'
        '</AudioPool><Tracks><Track Name="Voice"><Region Ref="1" Start="0" '
        'Length="1" Offset="0"/></Track></Tracks></Session>', encoding="utf-8")
    session = Session(tmp_path / "Missing.kuulas")
    try:
        session.command("import_nhsx", {"path": str(path)})
        assert not session.state.media
        assert len(session.last_import_report) == 1
        key = session.last_import_report[0].error.key
        assert key == "error.import.nhsx_missing_media"
    finally:
        session.close()


def test_bad_audio_costs_only_its_nhsx_region(tmp_path):
    write_audio(tmp_path / "good.wav")
    (tmp_path / "broken.wav").write_bytes(b"not a wave file")
    path = tmp_path / "partial.nhsx"
    path.write_text(
        '<Session><AudioPool><File Id="1" Name="good.wav"/><File Id="2" '
        'Name="broken.wav"/></AudioPool><Tracks><Track Name="Voice">'
        '<Region Ref="1" Start="0" Length="1" Offset="0"/>'
        '<Region Ref="2" Start="2" Length="1" Offset="0"/>'
        '</Track></Tracks></Session>', encoding="utf-8")
    session = Session(tmp_path / "Partial.kuulas")
    try:
        session.command("import_nhsx", {"path": str(path)})
        assert len(session.state.media) == 1
        assert len(session.state.tracks[0].clips) == 1
        assert len(session.last_import_report) == 2
        assert sum(not result.ok for result in session.last_import_report) == 1
    finally:
        session.close()


def test_import_nhsx_command_endpoint_returns_translated_bad_file(tmp_path):
    path = tmp_path / "broken.nhsx"
    path.write_text("<Session>", encoding="utf-8")
    session = Session(tmp_path / "Api.kuulas")
    try:
        app = create_app(session, Engine(), language="en", ui_dir=tmp_path)
        with TestClient(app) as client:
            response = client.post("/api/command", json={
                "name": "import_nhsx", "args": {"path": str(path)}})
        assert response.status_code == 400
        assert response.json()["error"]["key"] == "error.import.nhsx_failed"
    finally:
        session.close()
