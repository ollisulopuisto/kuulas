"""Export formats (WP11): the registry, what the installed ffmpeg offers, the
settings checks, and a real one-second encode of every format this machine has."""

import json
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import cli, export, export_formats
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000

# Recorded from `ffmpeg -hide_banner -encoders` (trimmed to the lines that
# matter): macOS, Homebrew build, with AudioToolbox.
HEADER = """\
Encoders:
 V..... = Video
 A..... = Audio
 S..... = Subtitle
 .F.... = Frame-level multithreading
 ..S... = Slice-level multithreading
 ...X.. = Codec is experimental
 ....B. = Supports draw_horiz_band
 .....D = Supports direct rendering method 1
 ------
 V....D libx264              libx264 H.264 (codec h264)
"""
BASE = """\
 A....D aac                  AAC (Advanced Audio Coding)
 A....D flac                 FLAC (Free Lossless Audio Codec)
 A....D libmp3lame           libmp3lame MP3 (MPEG audio layer 3) (codec mp3)
 A....D pcm_s16be            PCM signed 16-bit big-endian
 A....D pcm_s16le            PCM signed 16-bit little-endian
 A....D pcm_s24be            PCM signed 24-bit big-endian
 A....D pcm_s24le            PCM signed 24-bit little-endian
 A....D pcm_s32be            PCM signed 32-bit big-endian
 A....D pcm_s32le            PCM signed 32-bit little-endian
 A..X.D vorbis               Vorbis
 S..... srt                  SubRip subtitle
"""
AT = " A..... aac_at               aac (AudioToolbox) (codec aac)\n"
OPUS = " A....D libopus              libopus Opus (codec opus)\n"
VORBIS = " A....D libvorbis            libvorbis (codec vorbis)\n"
FDK = " A....D libfdk_aac           Fraunhofer FDK AAC (codec aac)\n"
MINIMAL = HEADER + (
    " A....D flac                 FLAC\n"
    " A....D pcm_s16be            x\n A....D pcm_s24be            x\n"
    " A....D pcm_s32be            x\n")
FULL = HEADER + BASE + AT + OPUS + VORBIS


def found(text: str):
    return export_formats.formats_for(export_formats.parse_encoders(text))


def ids(text: str) -> list[str]:
    return [f.id for f in found(text)]


def encoder_of(text: str, fmt: str) -> str | None:
    return next((f.encoder for f in found(text) if f.id == fmt), None)


HERE = export_formats.available_formats()
LOSSY_HERE = [f.id for f in HERE if not f.lossless]


# -- the registry and the parser --------------------------------------------------


def test_parse_encoders_reads_audio_lines_only():
    got = export_formats.parse_encoders(HEADER + BASE + AT)
    assert {"aac", "aac_at", "libmp3lame", "pcm_s24be", "flac"} <= got
    assert "libx264" not in got  # video
    assert "srt" not in got  # subtitle
    assert "Audio" not in got
    assert "=" not in got  # the legend is not an encoder list


def test_wav_flac_aiff_are_always_available():
    # Even an ffmpeg that offers nothing else, and no ffmpeg at all.
    assert ids(MINIMAL) == ["wav", "flac", "aiff"]
    assert ids("") == ["wav", "flac"]  # these two are written in-process


def test_wav_is_the_first_and_default_format():
    assert export_formats.DEFAULT == "wav"
    assert ids(HEADER + BASE)[0] == "wav"


def test_aac_prefers_audiotoolbox_then_aac_then_fdk():
    assert encoder_of(HEADER + BASE + AT, "m4a") == "aac_at"
    assert encoder_of(HEADER + BASE, "m4a") == "aac"
    assert encoder_of(MINIMAL + FDK, "m4a") == "libfdk_aac"
    assert encoder_of(MINIMAL, "m4a") is None


def test_opus_and_vorbis_need_their_libraries():
    assert "opus" not in ids(HEADER + BASE)  # the native opus encoder is experimental
    assert "ogg" not in ids(HEADER + BASE)  # so is the native vorbis
    assert encoder_of(HEADER + BASE + OPUS, "opus") == "libopus"
    assert encoder_of(HEADER + BASE + VORBIS, "ogg") == "libvorbis"


def test_only_aac_at_is_hardware_accelerated():
    assert {f.id: f.encoder for f in found(FULL) if f.accelerated} == {"m4a": "aac_at"}
    assert not [f for f in found(HEADER + BASE) if f.accelerated]


def test_every_format_describes_itself():
    got = found(FULL)
    assert [f.id for f in got] == ["wav", "flac", "mp3", "aiff", "m4a", "opus", "ogg"]
    assert {f.id: f.ext for f in got} == {
        "wav": "wav", "flac": "flac", "mp3": "mp3", "aiff": "aiff", "m4a": "m4a",
        "opus": "opus", "ogg": "ogg"}
    assert {f.id for f in got if f.lossless} == {"wav", "flac", "aiff"}
    for f in got:
        assert f.label_key == f"export.format.{f.id}"
        assert (f.kbps is None) == f.lossless
        if f.kbps:
            low, high = f.kbps
            assert low <= f.kbps_default[0] <= f.kbps_default[1] <= high


def test_available_formats_asks_ffmpeg_once(monkeypatch):
    calls = []

    def fake(cmd, **_kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=FULL, stderr="")

    export_formats.available_formats.cache_clear()
    monkeypatch.setattr(export_formats.subprocess, "run", fake)
    try:
        first = export_formats.available_formats()
        second = export_formats.available_formats()
    finally:
        export_formats.available_formats.cache_clear()
    assert first == second
    assert len(calls) == 1
    assert calls[0][:3] == ["ffmpeg", "-hide_banner", "-encoders"]
    assert "m4a" in [f.id for f in first]


def test_no_ffmpeg_leaves_the_in_process_formats(monkeypatch):
    def missing(*_a, **_kw):
        raise FileNotFoundError

    export_formats.available_formats.cache_clear()
    monkeypatch.setattr(export_formats.subprocess, "run", missing)
    try:
        assert [f.id for f in export_formats.available_formats()] == ["wav", "flac"]
    finally:
        export_formats.available_formats.cache_clear()


# -- settings -----------------------------------------------------------------------


def test_defaults_are_wav_24_bit_for_tracks_and_mix():
    for kind in ("mix", "tracks"):
        s = export._settings(kind, None, {})
        assert (s["format"], s["bit_depth"]) == ("wav", 24)


def test_unknown_or_unavailable_format_is_bad_format(monkeypatch):
    with pytest.raises(export.ExportError) as e:
        export._settings("mix", None, {"format": "wma"})
    assert e.value.key == "error.export.bad_format"
    only = found(MINIMAL)[:2]
    monkeypatch.setattr(export_formats, "available_formats", lambda: only)
    with pytest.raises(export.ExportError) as e:
        export._settings("mix", None, {"format": "aiff"})
    assert e.value.key == "error.export.bad_format"


@pytest.mark.parametrize("fmt", LOSSY_HERE)
def test_kbps_is_checked_against_the_formats_range(fmt):
    low, high = {f.id: f.kbps for f in HERE}[fmt]
    ok = export._settings("mix", None, {"format": fmt, "kbps": high})
    assert ok["mp3_kbps"] == high
    for bad in (low - 1, high + 1):
        with pytest.raises(export.ExportError) as e:
            export._settings("mix", None, {"format": fmt, "mp3_kbps": bad})
        assert e.value.key == "error.export.bad_kbps"


def test_a_remembered_bitrate_does_not_leak_into_another_format():
    s = export._settings("mix", {"format": "mp3", "mp3_kbps": 320}, {"format": "flac"})
    assert s["format"] == "flac"
    assert s["mp3_kbps"] is None


def test_flac_has_no_float_and_aiff_keeps_32():
    flac = export._settings("mix", None, {"format": "flac", "bit_depth": 32})
    assert flac["bit_depth"] == 24
    aiff = export._settings("mix", None, {"format": "aiff", "bit_depth": 32})
    assert aiff["bit_depth"] == 32


# -- a real encode of every format this machine has ---------------------------------


def probe(path: Path) -> dict:
    out = subprocess.run(  # noqa: S603 - fixed ffprobe executable, test output path
        [shutil.which("ffprobe") or "ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    src = tmp_path / "src"
    src.mkdir()
    rng = np.random.default_rng(7)
    audio = (rng.standard_normal(RATE) * 0.1).astype(np.float32)
    sf.write(src / "Olli.wav", audio, RATE, subtype="PCM_16")
    s.import_media([str(src / "Olli.wav")])
    yield s
    s.close()


def test_this_machine_has_the_three_that_must_exist():
    assert {"wav", "flac", "aiff"} <= {f.id for f in HERE}


@pytest.mark.parametrize("fmt", [f.id for f in HERE])
def test_a_one_second_mix_encodes_and_decodes(session, tmp_path, fmt):
    folder = str(tmp_path / "out")
    result = session.export({"kind": "mix", "format": fmt, "folder": folder})
    path = Path(result["path"])
    assert path.suffix == "." + {f.id: f.ext for f in HERE}[fmt]
    assert not list(path.parent.glob("*.partial"))
    info = probe(path)
    stream = info["streams"][0]
    assert int(stream["sample_rate"]) == RATE
    assert stream["channels"] == 2
    assert abs(float(info["format"]["duration"]) - session.state.length / RATE) < 0.05
    tags = {k.lower(): v for k, v in info["format"].get("tags", {}).items()}
    tags |= {k.lower(): v for k, v in stream.get("tags", {}).items()}
    if fmt != "wav":  # a WAV carries its provenance in the BWF chunk
        assert "kuulas" in " ".join(tags.values()), tags


@pytest.mark.parametrize("fmt", [f.id for f in HERE])
def test_a_track_export_in_every_format(session, tmp_path, fmt):
    result = session.export({"kind": "tracks", "format": fmt,
                             "folder": str(tmp_path / "out")})
    [file] = [Path(p) for p in result["paths"]]
    assert file.suffix == "." + {f.id: f.ext for f in HERE}[fmt]
    seconds = float(probe(file)["format"]["duration"])
    assert abs(seconds - session.state.length / RATE) < 0.05


@pytest.mark.parametrize("fmt", LOSSY_HERE)
def test_the_lossy_bitrate_is_used(session, tmp_path, fmt):
    low, high = {f.id: f.kbps for f in HERE}[fmt]
    want = min(max(96, low), high)
    result = session.export({"kind": "mix", "format": fmt, "kbps": want,
                             "folder": str(tmp_path / "out")})
    info = probe(Path(result["path"]))
    bit_rate = int(info["format"]["bit_rate"])
    # Opus and Vorbis are not constant-rate, and a one-second file carries container
    # overhead, so only a wide band is meaningful.
    assert want * 1000 * 0.5 < bit_rate < want * 1000 * 1.6, bit_rate


# -- the route, the job and the CLI --------------------------------------------------


class _NoEngine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


def client_for(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir(exist_ok=True)
    return TestClient(create_app(session, _NoEngine(), language="en", ui_dir=ui))


def test_the_formats_route(session, tmp_path):
    got = client_for(session, tmp_path).get("/api/export-formats").json()
    assert got[0]["id"] == "wav"
    assert set(got[0]) == {"id", "label", "ext", "lossless"}
    assert got[0]["lossless"] is True
    assert [f["id"] for f in got] == [f.id for f in HERE]


def test_export_mix_job_runs_in_the_background(session, tmp_path):
    [job_id] = session.export_mix({"format": "flac", "folder": str(tmp_path / "o")})
    deadline = time.monotonic() + 30
    job = None
    while time.monotonic() < deadline:
        job = next(j for j in session.jobs.list() if j["id"] == job_id)
        if job["state"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.01)
    assert job
    assert job["state"] == "completed", job
    assert Path(job["result"]["path"]).suffix == ".flac"
    assert session.last_export_folder == str(tmp_path / "o")


def test_export_mix_default_name_carries_project_and_time(session):
    args = session.mix_export_args({})
    assert args["kind"] == "mix"
    assert args["template"] == "{title} {stamp} v{n}.{ext}"
    assert "format" not in args  # the remembered or default (WAV) format applies


def test_export_mix_route(session, tmp_path):
    client = client_for(session, tmp_path)
    response = client.post("/api/export-mix", json={"format": "flac",
                                                    "folder": str(tmp_path / "o")})
    assert response.status_code == 202
    assert len(response.json()["jobs"]) == 1
    assert client.post("/api/export-mix", json={"format": "wma"}).status_code == 400


def test_cli_list_formats(capsys):
    assert cli.main(["export-tracks", "--list-formats"]) == 0
    lines = capsys.readouterr().out.split()
    assert lines[0] == "wav"
    assert lines == [f.id for f in HERE]


def test_cli_export_mix(session, tmp_path, capsys):
    folder = session.package.path
    session.close()
    out = tmp_path / "mixout"
    assert cli.main(["export-mix", str(folder), "--out", str(out),
                     "--format", "flac"]) == 0
    [file] = list(out.glob("*.flac"))
    assert abs(sf.info(file).duration - 1.0) < 0.05
    assert str(file) in capsys.readouterr().out


def test_cli_export_mix_kbps(session, tmp_path):
    folder = session.package.path
    session.close()
    out = tmp_path / "mixout"
    assert cli.main(["export-mix", str(folder), "--out", str(out),
                     "--format", "mp3", "--kbps", "96"]) == 0
    [file] = list(out.glob("*.mp3"))
    assert 90_000 < int(probe(file)["format"]["bit_rate"]) < 105_000


def test_cli_export_tracks_takes_any_registry_format(session, tmp_path):
    folder = session.package.path
    session.close()
    out = tmp_path / "stems"
    assert cli.main(["export-tracks", str(folder), "--out", str(out),
                     "--format", "aiff"]) == 0
    assert list(out.rglob("*.aiff"))


def test_cli_rejects_an_unknown_format(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cli.main(["export-mix", str(tmp_path), "--format", "wma"])
    assert capsys.readouterr().err


def test_cli_export_mix_needs_a_project(tmp_path, capsys):
    assert cli.main(["export-mix", str(tmp_path / "nope")]) == 1
    assert capsys.readouterr().err


def test_the_ui_lists_the_registry_formats():
    # ui/export-commands.js names the format ids it has commands for.
    text = Path("ui/export-commands.js").read_text(encoding="utf-8")
    block = text.split("EXPORT_FORMAT_IDS = [", 1)[1].split("]", 1)[0]
    listed = [s.strip(' "\n,') for s in block.split(",") if s.strip(' "\n,')]
    assert listed == [f.id for f in export_formats.ALL_FORMATS]
