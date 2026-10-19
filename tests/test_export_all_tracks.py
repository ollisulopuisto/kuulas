"""One-button "Export all tracks" and ``kuulas export-tracks``: the stems a
mixer such as the automixer takes, from a synthetic three-speaker project."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import cli, desktop, export, messages
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000
DASH = "\N{EN DASH}"


def voice(path: Path, seconds: float, seed: int) -> Path:
    rng = np.random.default_rng(seed)
    audio = (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32)
    sf.write(path, audio, RATE, subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    src = tmp_path / "src"
    src.mkdir()
    s.import_media([str(voice(src / "Olli.wav", 6, 1)),
                    str(voice(src / "Maija.wav", 6, 2)),
                    str(voice(src / "Ville.wav", 4, 3))])
    yield s
    s.close()


def wav(path) -> np.ndarray:
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    assert rate == RATE
    return data.T


def wait(session, job_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = next(j for j in session.jobs.list() if j["id"] == job_id)
        if job["state"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError(session.jobs.list())


def by_name(result) -> dict[str, Path]:
    return {Path(p).stem.split(f" {DASH} ")[1]: Path(p) for p in result["paths"]}


def test_every_track_is_a_file_with_the_same_start_and_length(session):
    [job_id] = session.export_tracks()
    job = wait(session, job_id)
    assert job["state"] == "completed", job
    result = job["result"]
    files = by_name(result)
    assert set(files) == {"Olli", "Maija", "Ville"}
    length = session.state.length
    assert {sf.info(p).frames for p in files.values()} == {length}
    # Ville is shorter than the edit: the tail is silence, the start is audio.
    ville = wav(files["Ville"])
    assert np.any(ville[:, : 4 * RATE])
    assert not np.any(ville[:, 4 * RATE :])
    assert result["track_count"] == 3
    assert result["silent"] == []


def test_the_default_is_dry_24_bit_wav_in_a_new_folder_beside_the_project(session):
    result = wait(session, session.export_tracks()[0])["result"]
    folder = Path(result["path"])
    assert folder.parent == session.package.path.parent / "Episode exports"
    assert folder.name.startswith("Main ")
    assert {sf.info(p).subtype for p in result["paths"]} == {"PCM_24"}
    assert result["settings"]["processing"] == "dry"
    session.edit("set_track", {"track_id": session.state.tracks[0].id, "gain_db": -3.0})
    again = wait(session, session.export_tracks()[0])["result"]
    assert Path(again["path"]) != folder  # nothing is overwritten
    assert folder.is_dir()
    assert Path(again["path"]).is_dir()


def test_soft_cuts_are_silent_and_clip_gain_and_mute_follow_the_edit(session, tmp_path):
    olli, maija, ville = session.state.tracks
    session.edit("mute_range", {"start": RATE, "end": 2 * RATE, "track_ids": [olli.id]})
    session.edit("set_clip", {"clip_id": maija.clips[0].id, "gain_db": -6.0})
    session.edit("set_track", {"track_id": ville.id, "mute": True})
    result = wait(session, session.export_tracks()[0])["result"]
    files = by_name(result)
    cut = wav(files["Olli"])
    assert not np.any(cut[:, RATE + 2400 : 2 * RATE - 2400])  # inside the 30 ms ramps
    assert np.any(cut[:, : RATE - 2400])
    assert np.any(cut[:, 2 * RATE + 2400 : 5 * RATE])
    source, _ = sf.read(tmp_path / "src" / "Maija.wav", dtype="float32")
    got = wav(files["Maija"])[0]
    np.testing.assert_allclose(got[RATE : 2 * RATE],
                               source[RATE : 2 * RATE] * 10 ** (-6 / 20), atol=1e-4)
    assert not np.any(wav(files["Ville"]))
    assert result["silent"] == ["Ville"]
    assert result["track_count"] == 3


def test_tracks_json_lists_every_track_with_name_kind_and_speaker(session):
    first = session.state.tracks[0].id
    session.edit("set_track", {"track_id": first, "speaker": "Olli S"})
    result = wait(session, session.export_tracks()[0])["result"]
    listing = json.loads((Path(result["path"]) / "tracks.json").read_text("utf-8"))
    assert [t["name"] for t in listing["tracks"]] == ["Olli", "Maija", "Ville"]
    assert {t["kind"] for t in listing["tracks"]} == {"speech"}
    assert listing["tracks"][0]["speaker"] == "Olli S"
    assert listing["tracks"][0]["file"] == f"Main {DASH} Olli.wav"
    assert listing["frames"] == session.state.length
    assert listing["start_frame"] == 0
    assert all(t["audible"] for t in listing["tracks"])


def test_a_music_track_is_named_so_the_automixer_finds_it_as_music(session):
    track = session.state.tracks[2]
    session.edit("set_track", {"track_id": track.id, "kind": "music", "name": "Intro"})
    result = wait(session, session.export_tracks()[0])["result"]
    assert f"Main {DASH} Intro MUSIC.wav" in {Path(p).name for p in result["paths"]}


def test_a_failure_is_a_failed_job_with_the_translated_text(tmp_path):
    empty = Session(tmp_path / "Empty.kuulas")
    try:
        job = wait(empty, empty.export_tracks()[0])
        assert job["state"] == "failed"
        assert job["error"]["text"] == messages.t("error.export.empty")
    finally:
        empty.close()


def test_cancel_stops_the_job_and_leaves_no_folder(session, monkeypatch):
    real = export._pump

    def slow(*a, **k):
        time.sleep(0.5)
        return real(*a, **k)

    monkeypatch.setattr(export, "_pump", slow)
    [job_id] = session.export_tracks()
    time.sleep(0.1)
    session.jobs.cancel(job_id)
    assert wait(session, job_id)["state"] == "cancelled"
    exports = session.package.path.parent / "Episode exports"
    assert not exports.exists() or not any(exports.iterdir())


class _NoEngine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


# -- the route and the CLI -----------------------------------------------------


def test_post_export_tracks_answers_with_one_job(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, _NoEngine(), language="en", ui_dir=ui)) as client:
        r = client.post("/api/export-tracks", json={})
        assert r.status_code == 202
        [job_id] = r.json()["jobs"]
        assert wait(session, job_id)["state"] == "completed"


def test_cli_export_tracks_prints_the_folder_and_files(session, tmp_path, capsys):
    folder = session.package.path
    session.close()
    out = tmp_path / "stems"
    assert cli.main(["export-tracks", str(folder), "--out", str(out),
                     "--format", "flac", "--bit-depth", "16"]) == 0
    printed = capsys.readouterr().out
    [made] = list(out.iterdir())
    assert str(made) in printed
    assert sorted(p.suffix for p in made.iterdir()) == [".flac"] * 3 + [".json"]
    assert "Olli" in printed


def test_cli_export_tracks_says_so_when_a_window_holds_it(session, tmp_path, capsys):
    folder = session.package.path
    session.close()
    beat = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    (folder / "lock.json").write_text(json.dumps({
        "host": "windows-pc", "pid": 4242, "user": "ville", "opened_utc": beat,
        "heartbeat_utc": beat}))
    code = cli.main(["export-tracks", str(folder), "--out", str(tmp_path / "o")])
    assert code == 1
    assert capsys.readouterr().err.strip() == messages.t("error.history.read_only",
                                                         host="windows-pc")
    assert not (tmp_path / "o").exists()


def test_cli_export_tracks_reports_a_bad_project(tmp_path, capsys):
    (tmp_path / "file").write_text("x")
    assert cli.main(["export-tracks", str(tmp_path / "file")]) == 1
    assert capsys.readouterr().err


# -- show in Finder ------------------------------------------------------------


@pytest.mark.parametrize(("platform", "command"), [
    ("darwin", ["open", "-R"]),
    ("win32", ["explorer"]),
    ("linux", ["xdg-open"]),
])
def test_reveal_command_per_platform(platform, command, tmp_path):
    got = desktop.reveal_command(tmp_path, platform)
    assert got[: len(command)] == command
    assert str(tmp_path) in got[-1]
    assert platform != "win32" or got[-1].startswith("/select,")


def test_bridge_reveals_only_the_last_export_folder(session, tmp_path):
    ran = []
    bridge = desktop.Bridge(object(), tmp_path / "recents")
    bridge._runner = ran.append

    class Running:
        _session = session

    bridge._project = Running()
    assert bridge.reveal_export() is False  # nothing exported yet
    result = wait(session, session.export_tracks()[0])["result"]
    assert bridge.reveal_export() is True
    assert str(result["path"]) in ran[0][-1]


# -- the native folder chooser and the remembered folder -------------------------


class _FakeWebview:
    class FileDialog:
        FOLDER = "folder"


class _FakeWindow:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def create_file_dialog(self, kind, **options):
        self.calls.append((kind, options))
        return self.answer


def _bridge(tmp_path, answer):
    bridge = desktop.Bridge(_FakeWebview, tmp_path / "recents")
    bridge._window = _FakeWindow(answer)
    return bridge


def test_choose_export_folder_returns_the_folder(tmp_path):
    start = tmp_path / "Episode exports"
    start.mkdir()
    bridge = _bridge(tmp_path, [str(tmp_path / "out")])
    assert bridge.choose_export_folder(str(start)) == str(tmp_path / "out")
    [(kind, options)] = bridge._window.calls
    assert kind == "folder"
    assert options["directory"] == str(start)


def test_choose_export_folder_none_on_cancel(tmp_path):
    assert _bridge(tmp_path, None).choose_export_folder(str(tmp_path)) is None
    assert _bridge(tmp_path, []).choose_export_folder(str(tmp_path)) is None


@pytest.mark.parametrize("bad", [None, 3, ["x"], {"a": 1}, "bad\0path"])
def test_choose_export_folder_rejects_a_start_that_is_not_a_string(tmp_path, bad):
    bridge = _bridge(tmp_path, [str(tmp_path)])
    assert bridge.choose_export_folder(bad) is None
    assert bridge._window.calls == []


def test_choose_export_folder_starts_at_the_nearest_existing_folder(tmp_path):
    bridge = _bridge(tmp_path, None)
    bridge.choose_export_folder(str(tmp_path / "Episode exports"))
    assert bridge._window.calls[0][1]["directory"] == str(tmp_path)


def test_export_folder_hint_defaults_next_to_the_project(session, tmp_path):
    hint = session.export_folder_hint()
    assert hint == {"folder": str(tmp_path / "Episode exports"), "remembered": False}
    assert not (tmp_path / "Episode exports").exists()  # made only on export


def test_chosen_folder_is_the_parent_and_is_remembered(session, tmp_path):
    chosen = tmp_path / "elsewhere"
    result = wait(session, session.export_tracks({"folder": str(chosen)})[0])["result"]
    assert Path(result["path"]).parent == chosen
    assert Path(result["path"]).is_dir()
    assert session.export_folder_hint() == {"folder": str(chosen), "remembered": True}


def test_get_export_folder_route(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, _NoEngine(), language="en", ui_dir=ui)) as client:
        r = client.get("/api/export-folder")
        default = str(tmp_path / "Episode exports")
        assert r.json() == {"folder": default, "remembered": False}


def test_tracks_json_lists_hand_made_mutes_and_gate_apart_on_the_stem_clock(session):
    olli, maija, ville = session.state.tracks
    session.edit("mute_range", {"start": RATE, "end": 2 * RATE, "track_ids": [olli.id]})
    session.edit("set_gate", {"track_id": maija.id, "ranges": [[3 * RATE, 4 * RATE]]})
    session.edit("set_track", {"track_id": ville.id, "mute": True})
    result = wait(session, session.export_tracks()[0])["result"]
    listing = json.loads((Path(result["path"]) / "tracks.json").read_text("utf-8"))
    o, m, v = listing["tracks"]
    assert o["muted_frames"] == [[RATE, 2 * RATE]]
    assert "gate_frames" not in o
    assert m["gate_frames"] == [[3 * RATE, 4 * RATE]]
    assert "muted_frames" not in m
    assert not v["audible"]
    assert "muted_frames" not in v
    assert "gate_frames" not in v
