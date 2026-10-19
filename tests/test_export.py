"""Export (WP11): mix, selection and tracks, one engine."""

import errno
import json
import os
import shutil
import struct
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pyloudnorm
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import export, messages, mixer, ops
from kuulas.media import wav_header
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


def noise(path: Path, seconds: float, seed: int, channels: int = 1) -> Path:
    rng = np.random.default_rng(seed)
    n = round(seconds * RATE)
    shape = (n,) if channels == 1 else (n, channels)
    sf.write(path, (rng.standard_normal(shape) * 0.1).astype(np.float32), RATE,
             subtype="PCM_16")
    return path


def dialogue_noise(path: Path, seconds: float, seed: int, channels: int = 1) -> Path:
    """Deterministic speech-band noise; white noise exaggerates MP3 low-pass loss."""
    rng = np.random.default_rng(seed)
    n = round(seconds * RATE)
    shape = (n,) if channels == 1 else (n, channels)
    audio = rng.standard_normal(shape)
    frequencies = np.fft.rfftfreq(n, 1 / RATE)
    spectrum = np.fft.rfft(audio, axis=0)
    spectrum[(frequencies < 80) | (frequencies > 12_000)] = 0
    audio = np.fft.irfft(spectrum, n=n, axis=0)
    audio *= 0.1 / np.sqrt(np.mean(audio**2))
    sf.write(path, audio.astype(np.float32), RATE, subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path):
    """Three tracks: two mono voices of different lengths and a stereo one."""
    s = Session(tmp_path / "Talk.kuulas")
    src = tmp_path / "src"
    src.mkdir()
    s.import_media([str(noise(src / "a.wav", 5, 1)), str(noise(src / "b.wav", 3, 2)),
                    str(noise(src / "m.wav", 4, 3, channels=2))])
    yield s
    s.close()


@pytest.fixture
def out(tmp_path):
    return tmp_path / "out"


def run(session, out, **args):
    return session.export({"folder": str(out), "format": "wav", "bit_depth": 32,
                           "kind": "mix", **args})


def float_wav(path) -> np.ndarray:
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    assert rate == RATE
    return data.T


def whole_mix(session) -> np.ndarray:
    p = session.state
    return mixer.mix(p, session.store, 0, p.length)


def ffmpeg_decode(path: Path) -> np.ndarray:
    binary = shutil.which("ffmpeg")
    assert binary is not None
    raw = subprocess.run(  # noqa: S603 - fixed ffmpeg executable and test output path
        [binary, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2",
         "-ar", str(RATE), "-"], capture_output=True, check=True
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T


def lufs(audio: np.ndarray) -> float:
    return pyloudnorm.Meter(RATE).integrated_loudness(audio.T.astype(np.float64))


def bext(path: Path) -> dict:
    blob = path.read_bytes()
    at = blob.index(b"bext")
    size = struct.unpack_from("<I", blob, at + 4)[0]
    body = blob[at + 8:at + 8 + size]
    return {"description": body[:256].split(b"\0")[0].decode("utf-8"),
            "originator": body[256:288].split(b"\0")[0].decode("ascii"),
            "time_reference": struct.unpack_from("<Q", body, 338)[0]}


# -- the mix ----------------------------------------------------------------


def test_float_wav_export_equals_the_mixer_bit_exact(session, out):
    r = run(session, out)
    assert Path(r["path"]).name == "Main v1.wav"
    assert np.array_equal(float_wav(r["path"]), whole_mix(session))


class _Clock:
    """Stands in for ``export.datetime``: ``now`` moves ``step`` seconds per call."""

    def __init__(self, step: float):
        self.at = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
        self.step = step

    def now(self, tz=None):
        self.at += timedelta(seconds=self.step)
        return self.at


#: The bext origination time ("HH:MM:SS"): 12 + 8 + 256 + 32 + 32 + 10 into the file.
BEXT_TIME = slice(350, 358)


def test_two_wav_exports_differ_only_in_the_bext_origination_time(
        session, out, monkeypatch):
    # The "flaky" parallel-vs-serial failure: bext stamps the wall clock to the
    # second, so two exports that straddle a second boundary differ in that
    # one field and nowhere else (audio, sizes, everything else identical).
    monkeypatch.setattr(export, "datetime", _Clock(step=1))
    monkeypatch.setattr(export, "BLOCK_SECONDS", 0.7)
    a = Path(run(session, out / "a", workers=1)["path"]).read_bytes()
    b = Path(run(session, out / "b", workers=4)["path"]).read_bytes()
    assert a[BEXT_TIME] != b[BEXT_TIME]
    cut = BEXT_TIME
    assert a[:cut.start] + a[cut.stop:] == b[:cut.start] + b[cut.stop:]


def test_parallel_and_serial_renders_are_identical(session, out, monkeypatch):
    monkeypatch.setattr(export, "BLOCK_SECONDS", 0.7)  # several blocks
    monkeypatch.setattr(export, "datetime", _Clock(step=0))  # bext stamps the second
    serial = run(session, out / "s", workers=1)
    parallel = run(session, out / "p", workers=4)
    assert Path(serial["path"]).read_bytes() == Path(parallel["path"]).read_bytes()
    assert np.array_equal(float_wav(parallel["path"]), whole_mix(session))


def test_a_crash_mid_render_leaves_nothing_at_the_target(session, out, monkeypatch):
    monkeypatch.setattr(export, "BLOCK_SECONDS", 0.7)
    real, calls = mixer.mix, []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError("boom")
        return real(*args, **kwargs)

    monkeypatch.setattr(mixer, "mix", flaky)
    with pytest.raises(RuntimeError, match="boom"):
        run(session, out)
    assert list(out.rglob("*")) == []
    assert session.history.checkpoints() == []
    # ...and the failed attempt used no version number.
    monkeypatch.setattr(mixer, "mix", real)
    assert Path(run(session, out)["path"]).name == "Main v1.wav"


def test_a_full_disk_costs_the_export_not_the_session(session, out, monkeypatch):
    def full(*_args, **_kwargs):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(export._WavWriter, "write", full)
    with pytest.raises(export.ExportError) as e:
        run(session, out)
    assert e.value.key == "error.export.cannot_write"
    assert list(out.rglob("*")) == []


def test_an_unwritable_folder_says_so(session, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(export.ExportError) as e:
        run(session, blocker / "inside")
    assert e.value.key == "error.export.cannot_write"


def test_cancel_stops_and_cleans_up(session, out, monkeypatch):
    monkeypatch.setattr(export, "BLOCK_SECONDS", 0.5)
    stop = threading.Event()

    def progress(fraction, _message=""):
        if fraction > 0.2:
            stop.set()

    with pytest.raises(export.ExportError) as e:
        session.export({"folder": str(out), "kind": "mix", "format": "wav"},
                       progress=progress, cancel=stop)
    assert e.value.key == "error.export.cancelled"
    assert list(out.rglob("*")) == []


def test_progress_reaches_one(session, out):
    seen = []
    session.export({"folder": str(out), "kind": "mix", "format": "wav"},
                   progress=lambda f, _m="": seen.append(f))
    assert seen == sorted(seen)
    assert seen[-1] == 1.0


def test_bit_depths_and_flac(session, out):
    mix = whole_mix(session)
    for depth, tolerance in ((16, 2 ** -14), (24, 2 ** -22)):
        r = run(session, out / str(depth), bit_depth=depth)
        np.testing.assert_allclose(float_wav(r["path"]), mix, atol=tolerance)
    r = run(session, out, format="flac", bit_depth=24)
    assert Path(r["path"]).name == "Main v1.flac"
    np.testing.assert_allclose(float_wav(r["path"]), mix, atol=2 ** -22)


def test_wav_carries_bwf_time_reference_and_provenance(session, out):
    r = run(session, out)
    head = wav_header(Path(r["path"]))
    assert head["time_reference"] == 0
    box = bext(Path(r["path"]))
    assert box["time_reference"] == 0
    assert box["originator"] == "kuulas"
    for part in ("Main", "Talk", "v1", session.history.head):
        assert part in box["description"]


def test_mp3_decodes_with_the_same_length_and_loudness(tmp_path, out):
    # Broadband white noise has energy above MP3's 128 kbps low-pass and is an
    # invalid proxy for programme audio; measure a speech-band fixture instead.
    session = Session(tmp_path / "Dialogue.kuulas")
    source = tmp_path / "source"
    source.mkdir()
    session.import_media([
        str(dialogue_noise(source / "a.wav", 5, 1)),
        str(dialogue_noise(source / "b.wav", 3, 2)),
        str(dialogue_noise(source / "m.wav", 4, 3, channels=2)),
    ])
    try:
        wav = run(session, out / "w")
        mp3 = run(session, out / "m", format="mp3", mp3_kbps=128)
        assert Path(mp3["path"]).name == "Main v1.mp3"
        reference, decoded = float_wav(wav["path"]), ffmpeg_decode(Path(mp3["path"]))
        assert abs(decoded.shape[1] - reference.shape[1]) <= 1152
        assert abs(lufs(decoded) - lufs(reference)) < 0.5
    finally:
        session.close()


def test_mp3_tags_say_where_it_came_from(session, out):
    r = run(session, out, format="mp3", mp3_kbps=96)
    binary = shutil.which("ffprobe")
    assert binary is not None
    info = json.loads(subprocess.run(  # noqa: S603 - fixed ffprobe and test output path
        [binary, "-v", "error", "-show_format", "-of", "json", r["path"]],
        capture_output=True, check=True, text=True
    ).stdout)
    tags = {k.lower(): v for k, v in info["format"]["tags"].items()}
    assert tags["title"] == "Main"
    assert tags["album"] == "Talk"
    assert "v1" in tags["comment"]
    assert session.history.head in tags["comment"]
    assert 90_000 < int(info["format"]["bit_rate"]) < 100_000


def test_numba_cache_dir_is_set_and_writable():
    cache_path = os.environ.get("NUMBA_CACHE_DIR")
    assert cache_path is not None, "NUMBA_CACHE_DIR is not set"
    cache = Path(cache_path)
    assert cache.is_dir()
    probe = cache / ".probe_write"
    probe.write_text("ok")
    probe.unlink()


def test_mastering_reaches_the_target(session, out):
    r = run(session, out, master_lufs=-16.0)
    assert lufs(float_wav(r["path"])) == pytest.approx(-16.0, abs=0.5)
    assert set(r["master"]) == {"boost_db", "lufs", "cost_lu", "reached"}
    assert r["master"]["reached"] is True


def test_mastering_refuses_programmes_too_long_for_memory(session, out, monkeypatch):
    monkeypatch.setattr(export, "MAX_MASTER_SECONDS", 1)
    with pytest.raises(export.ExportError) as e:
        run(session, out, master_lufs=-16.0)
    assert e.value.key == "error.export.too_long_to_master"
    assert list(out.rglob("*")) == []


@pytest.mark.parametrize("args", [
    {"format": "ogg"}, {"bit_depth": 20}, {"format": "mp3", "mp3_kbps": 500},
    {"kind": "reel"}, {"kind": "selection"}, {"kind": "selection", "range": [5, 5]},
    {"master_lufs": "loud"},
])
def test_bad_settings_are_refused_before_anything_is_written(session, out, args):
    with pytest.raises(export.ExportError):
        run(session, out, **args)
    assert not out.exists() or list(out.rglob("*")) == []


def test_an_empty_edit_has_nothing_to_export(tmp_path):
    empty = Session(tmp_path / "Empty.kuulas")
    try:
        with pytest.raises(export.ExportError) as e:
            empty.export({"folder": str(tmp_path / "o"), "kind": "mix",
                          "format": "wav"})
        assert e.value.key == "error.export.empty"
    finally:
        empty.close()


# -- versions, names, checkpoints ------------------------------------------------


def test_unchanged_edit_is_not_rendered_again(session, out):
    first = run(session, out)
    again = run(session, out)
    assert again["skipped"] is True
    assert again["unchanged_since"] == 1
    assert again["path"] == first["path"]
    assert "Unchanged since v1" in again["message"]
    assert sorted(p.name for p in out.iterdir()) == ["Main v1.wav"]


def test_a_changed_edit_or_setting_counts_up(session, out):
    run(session, out)
    track = session.state.tracks[0].id
    session.edit("set_track", {"track_id": track, "gain_db": -3.0})
    second = run(session, out)
    assert Path(second["path"]).name == "Main v2.wav"
    assert not second["skipped"]
    third = run(session, out, bit_depth=24)
    assert Path(third["path"]).name == "Main v3.wav"
    # Undo returns to a state exported before, but the last export was another.
    session.undo()
    fourth = run(session, out)
    assert Path(fourth["path"]).name == "Main v4.wav"


def test_a_deleted_export_is_made_again_under_its_own_number(session, out):
    first = run(session, out)
    Path(first["path"]).unlink()
    again = run(session, out)
    assert Path(again["path"]).name == "Main v1.wav"
    assert not again["skipped"]


def test_existing_files_are_never_overwritten(session, out):
    out.mkdir()
    (out / "Main v1.wav").write_bytes(b"precious")
    r = run(session, out)
    assert Path(r["path"]).name == "Main v2.wav"
    assert (out / "Main v1.wav").read_bytes() == b"precious"


def test_latest_copy_follows_the_newest_version(session, out):
    r = run(session, out, latest=True)
    latest = out / "Main latest.wav"
    assert latest.read_bytes() == Path(r["path"]).read_bytes()
    session.edit("set_track", {"track_id": session.state.tracks[0].id, "gain_db": -3.0})
    r2 = run(session, out, latest=True)
    assert latest.read_bytes() == Path(r2["path"]).read_bytes()


def test_latest_copy_can_be_enabled_without_rerendering(session, out):
    first = run(session, out)

    second = run(session, out, latest=True)

    latest = out / "Main latest.wav"
    assert second["skipped"] is True
    assert latest.read_bytes() == Path(first["path"]).read_bytes()
    assert session.last_export_settings("mix")["latest"] is True
    assert not list(out.glob("*.partial"))


def test_the_name_template_is_the_users(session, out):
    r = run(session, out, template="{edit}_{n}.{ext}")
    assert Path(r["path"]).name == "Main_1.wav"


def test_each_export_is_a_checkpoint_of_the_step_it_rendered(session, out):
    head = session.history.head
    run(session, out, bit_depth=24)
    [cp] = session.history.checkpoints()
    assert cp["kind"] == "export"
    assert cp["node"] == head
    assert cp["name"] == "v1 exported, WAV 24-bit"
    run(session, out, bit_depth=24)  # skipped: no second checkpoint
    assert len(session.history.checkpoints()) == 1


def test_finnish_messages(session, out):
    messages.set_language("fi")
    run(session, out)
    again = run(session, out)
    assert "Ei muutoksia" in again["message"]
    [cp] = session.history.checkpoints()
    assert "vietiin" in cp["name"] or "viety" in cp["name"]


def test_last_settings_are_remembered_per_kind_for_quick_export(session, out):
    assert session.last_export_settings("mix") is None
    run(session, out, format="mp3", mp3_kbps=96)
    saved = session.last_export_settings("mix")
    assert saved["format"] == "mp3"
    assert saved["mp3_kbps"] == 96
    assert session.last_export_settings("tracks") is None
    session.edit("set_track", {"track_id": session.state.tracks[0].id, "gain_db": -3.0})
    quick = session.export({"kind": "mix"})  # nothing but the kind: the remembered ones
    assert Path(quick["path"]).name == "Main v2.mp3"
    assert Path(quick["path"]).parent == out


def test_settings_survive_reopening(tmp_path, out):
    folder = tmp_path / "Reopen.kuulas"
    first = Session(folder)
    first.import_media([str(noise(tmp_path / "a.wav", 2, 1))])
    run(first, out, bit_depth=24)
    first.close()
    second = Session(folder)
    try:
        assert second.last_export_settings("mix")["bit_depth"] == 24
        assert run(second, out, bit_depth=24)["skipped"] is True
    finally:
        second.close()


# -- selection -----------------------------------------------------------------


def edge_gains(n: int, fade: int) -> np.ndarray:
    gains = np.ones(n)
    ramp = np.sin(0.5 * np.pi * np.arange(fade) / fade) ** 2
    gains[:fade] *= ramp
    gains[n - fade:] *= ramp[::-1]
    return gains


def test_selection_is_that_range_of_the_mix_with_edge_fades(session, out):
    a, b = RATE, 3 * RATE + 100
    r = run(session, out, kind="selection", range=[a, b])
    got = float_wav(r["path"])
    fade = round(0.030 * RATE)
    expected = whole_mix(session)[:, a:b] * edge_gains(b - a, fade)
    np.testing.assert_allclose(got, expected, atol=1e-6)
    assert got[:, 0].tolist() == [0.0, 0.0]
    assert Path(r["path"]).name == "Main 0m01s\N{EN DASH}0m03s v1.wav"
    assert bext(Path(r["path"]))["time_reference"] == a


def test_selection_defaults_to_mp3(session, out):
    r = session.export({"folder": str(out), "kind": "selection", "range": [0, RATE]})
    assert Path(r["path"]).suffix == ".mp3"


def test_selection_past_the_end_is_clamped_and_a_tiny_one_still_fades(session, out):
    r = run(session, out, kind="selection", range=[4 * RATE, 99 * RATE])
    assert float_wav(r["path"]).shape[1] == RATE  # the edit is 5 s long
    r = run(session, out / "tiny", kind="selection", range=[0, 100])
    assert float_wav(r["path"]).shape[1] == 100


# -- tracks --------------------------------------------------------------------


def tracks_out(r) -> dict[str, Path]:
    return {p.stem.split(" \N{EN DASH} ")[1]: p for p in map(Path, r["paths"])}


def test_tracks_are_aligned_equal_length_and_keep_their_channels(session, out):
    r = run(session, out, kind="tracks")
    folder = Path(r["path"])
    assert folder.name == "Main tracks v1"
    files = tracks_out(r)
    assert set(files) == {"a", "b", "m"}
    assert {p.name for p in files.values()} == {
        "Main \N{EN DASH} a.wav", "Main \N{EN DASH} b.wav",
        "Main \N{EN DASH} m.wav"}
    length = session.state.length
    assert {sf.info(p).frames for p in files.values()} == {length}
    assert [sf.info(files[n]).channels for n in ("a", "b", "m")] == [1, 1, 2]
    assert all(bext(p)["time_reference"] == 0 for p in files.values())
    # b is shorter than the edit: its tail is silence.
    b = float_wav(files["b"])
    assert np.all(b[:, 3 * RATE:] == 0.0)
    assert np.any(b[:, :3 * RATE] != 0.0)


def test_tracks_default_to_24_bit_wav(session, out):
    r = session.export({"folder": str(out), "kind": "tracks"})
    assert {sf.info(p).subtype for p in r["paths"]} == {"PCM_24"}


def with_track_effects(session):
    a, b = session.state.tracks[0].id, session.state.tracks[1].id
    session.edit("set_track", {"track_id": a, "gain_db": -6.0})
    session.edit("set_track_automation", {"track_id": b, "points": [[0, -9.0]]})
    session.edit("set_clip", {"clip_id": session.state.tracks[0].clips[0].id,
                              "gain_db": -2.0})  # clip gain is part of the edit


def centred_sum(files: dict[str, Path], length: int) -> np.ndarray:
    total = np.zeros((2, length))
    for p in files.values():
        stem = float_wav(p)
        total += (stem if stem.shape[0] == 2 else np.repeat(stem, 2, axis=0)
                  * np.sqrt(0.5))
    return total


def test_dry_tracks_sum_to_the_dry_mix_and_leave_out_track_effects(session, out):
    with_track_effects(session)
    r = run(session, out, kind="tracks", processing="dry")
    p = session.state
    dry = p
    for t in p.tracks:
        dry = ops.set_track_automation(ops.set_track(dry, t.id, gain_db=0.0), t.id, [])
    expected = mixer.mix(dry, session.store, 0, p.length)
    np.testing.assert_allclose(centred_sum(tracks_out(r), p.length), expected,
                               atol=1e-6)


def test_as_heard_tracks_match_their_contribution_to_the_mix(session, out):
    with_track_effects(session)
    r = run(session, out, kind="tracks", processing="as_heard")
    p = session.state
    files = tracks_out(r)
    for track in p.tracks:
        alone = ops.set_track(p, track.id, solo=True)
        expected = mixer.mix(alone, session.store, 0, p.length)
        stem = float_wav(files[track.name])
        got = (stem if stem.shape[0] == 2
               else np.repeat(stem, 2, axis=0) * np.sqrt(0.5))
        np.testing.assert_allclose(got, expected, atol=1e-6)


def test_a_muted_clip_is_silence_in_the_track_file(session, out):
    clip = session.state.tracks[0].clips[0].id
    session.edit("set_clip", {"clip_id": clip, "muted": True})
    r = run(session, out, kind="tracks")
    assert not np.any(float_wav(tracks_out(r)["a"]))


def test_a_muted_track_is_silence_in_dry_and_as_heard_stems(session, out):
    track = session.state.tracks[0].id
    session.edit("set_track", {"track_id": track, "mute": True})

    for processing in ("dry", "as_heard"):
        r = run(session, out / processing, kind="tracks", processing=processing)
        assert not np.any(float_wav(tracks_out(r)["a"]))


def test_tracks_of_a_selection_start_together_at_the_selection(session, out):
    a, b = RATE, 2 * RATE
    r = run(session, out, kind="tracks", range=[a, b])
    assert Path(r["path"]).name == "Main 0m01s\N{EN DASH}0m02s tracks v1"
    for p in map(Path, r["paths"]):
        assert sf.info(p).frames == RATE
        assert bext(p)["time_reference"] == a
    whole = float_wav(tracks_out(run(session, out / "w", kind="tracks"))["a"])
    cut = float_wav(tracks_out(r)["a"])
    fade = round(0.030 * RATE)
    np.testing.assert_allclose(cut, whole[:, a:b] * edge_gains(b - a, fade), atol=1e-6)


def test_a_failed_tracks_export_leaves_no_folder(session, out, monkeypatch):
    monkeypatch.setattr(export, "BLOCK_SECONDS", 0.7)

    def flaky(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(mixer, "track_stem", flaky)
    with pytest.raises(RuntimeError):
        run(session, out, kind="tracks")
    assert list(out.rglob("*")) == []


def test_tracks_skip_when_unchanged_and_never_overwrite(session, out):
    first = run(session, out, kind="tracks")
    again = run(session, out, kind="tracks")
    assert again["skipped"]
    assert again["path"] == first["path"]
    run(session, out, kind="tracks", processing="as_heard")
    assert sorted(p.name for p in out.iterdir()) == ["Main tracks v1", "Main tracks v2"]


def test_tracks_list_file_lets_the_session_be_rebuilt(session, out):
    r = run(session, out, kind="tracks", list_file=True)
    listing = json.loads((Path(r["path"]) / "tracks.json").read_text("utf-8"))
    assert [t["name"] for t in listing["tracks"]] == ["a", "b", "m"]
    assert listing["tracks"][0]["file"] == "Main \N{EN DASH} a.wav"
    assert listing["start_frame"] == 0
    assert listing["rate"] == RATE
    assert listing["processing"] == "dry"


# -- the API -------------------------------------------------------------------


class _NoEngine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


@pytest.fixture
def client(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, _NoEngine(), language="en", ui_dir=ui)) as c:
        yield c


def test_post_export_renders_and_answers_with_the_result(client, session, out):
    r = client.post("/api/export", json={"kind": "mix", "folder": str(out),
                                         "format": "wav", "bit_depth": 16})
    assert r.status_code == 200, r.text
    body = r.json()
    assert Path(body["export"]["path"]).name == "Main v1.wav"
    assert (out / "Main v1.wav").is_file()
    assert body["export"]["skipped"] is False
    assert body["head"] == session.history.head
    again = client.post("/api/export", json={"kind": "mix", "folder": str(out),
                                             "format": "wav", "bit_depth": 16}).json()
    assert again["export"]["skipped"] is True


def test_post_export_refuses_a_bad_request_with_a_translated_error(client, out):
    r = client.post("/api/export", json={"kind": "mix", "folder": str(out),
                                         "format": "ogg"},
                    headers={"Accept-Language": "fi"})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.export.bad_format"
    assert r.json()["error"]["text"] != "error.export.bad_format"
    assert not out.exists()


def test_the_two_catalogs_have_the_export_messages():
    for lang in messages.LANGUAGES:
        keys = {k for k in messages._CATALOGS[lang] if "export" in k}
        assert {"error.export.cancelled", "history.export"} <= keys


def test_ffmpeg_is_present_for_mp3():
    assert shutil.which("ffmpeg")


def test_tracks_list_counts_mutes_from_the_stems_first_sample(session, out):
    track = session.state.tracks[0].id
    session.edit("mute_range", {"start": RATE // 2, "end": 3 * RATE // 2,
                                "track_ids": [track]})
    r = run(session, out, kind="tracks", range=[RATE, 2 * RATE], list_file=True)
    listing = json.loads((Path(r["path"]) / "tracks.json").read_text("utf-8"))
    assert listing["start_frame"] == RATE
    assert listing["tracks"][0]["muted_frames"] == [[0, RATE // 2]]
    assert "muted_frames" not in listing["tracks"][1]
