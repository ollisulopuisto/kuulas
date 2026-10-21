"""Automix of the In/Out range only (a quick preview): the stems are just the range,
range-relative, and the automixer's folder route still sees ``start_frame`` 0.

The automixer is a fake runner (a Python function standing in for the process), as in
the ``run_process`` tests of test_automix.py; no real automixer, no audio playback."""

import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import automix, export, messages
from kuulas.session import Session

RATE = 48000
A, B = RATE, 2 * RATE + RATE // 2  # 0:01.0 to 0:02.5


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


def noise(path: Path, seconds: float, seed: int) -> Path:
    rng = np.random.default_rng(seed)
    audio = (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32)
    sf.write(path, audio, RATE, subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    src = tmp_path / "src"
    src.mkdir()
    s.import_media([str(noise(src / "Olli.wav", 3, 1)),
                    str(noise(src / "Maija.wav", 3, 2))])
    yield s
    s.close()


class FakeAutomixer:
    """The automixer as a ``run_process``: records the stems it was given and writes a
    stereo 24-bit mix as long as the stems."""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, cmd, cwd, on_line, cancel):
        del cwd, cancel
        if "--help" in cmd:
            return 0
        folder = Path(cmd[1])
        listing = json.loads((folder / "tracks.json").read_text("utf-8"))
        stems = {t["name"]: sf.read(folder / t["file"], dtype="float32",
                                    always_2d=True)[0]
                 for t in listing["tracks"]}
        self.calls.append({"listing": listing, "stems": stems})
        out = Path(cmd[cmd.index("-o") + 1])
        sf.write(out, np.full((listing["frames"], 2), 0.25, dtype=np.float32), RATE,
                 subtype="PCM_24")
        on_line("PROGRESS 100 done")
        return 0


def settings(tmp_path) -> dict:
    return {"command": ["automixer"], "cwd": str(tmp_path), "extra_args": []}


def run(session, tmp_path, fake, **params):
    return automix.run(session, params, settings(tmp_path), lambda *a, **k: None,
                       threading.Event(), run_process=fake)


def test_a_range_run_gets_range_relative_stems_with_start_frame_zero(session, tmp_path):
    fake = FakeAutomixer()
    run(session, tmp_path, fake, range=[A, B])
    [called] = fake.calls
    listing = called["listing"]
    # The folder route requires start_frame 0 and frames equal to every file.
    assert listing["start_frame"] == 0
    assert listing["frames"] == B - A
    assert listing["rate"] == automix.MANIFEST_RATE
    for stem in called["stems"].values():
        assert stem.shape[0] == B - A
    # Frame 0 of the stem is the timeline's frame A (past the short fade a ranged
    # export puts at each edge, so the excerpt does not start with a click).
    source, _ = sf.read(tmp_path / "src" / "Olli.wav", dtype="float32")
    edge = RATE // 10
    np.testing.assert_allclose(called["stems"]["Olli"][edge:-edge, 0],
                               source[A + edge:B - edge], atol=2e-4)


def test_the_range_render_is_named_preview_with_its_span_and_says_so(session, tmp_path):
    fake = FakeAutomixer()
    result = run(session, tmp_path, fake, range=[A, B])
    assert result["name"].endswith(" preview 00.01-00.02.wav")
    assert result["range"] == [A, B]
    log = Path(result["log_file"]).read_text("utf-8")
    assert "Range preview 00:01-00:02: levels measured on the excerpt only" in log
    assert sf.info(result["path"]).frames == B - A


def test_a_full_run_has_no_range(session, tmp_path):
    result = run(session, tmp_path, FakeAutomixer())
    assert result["range"] is None
    assert " preview " not in result["name"]
    assert "Range preview" not in Path(result["log_file"]).read_text("utf-8")


def test_a_range_render_never_overwrites_an_earlier_file(session, tmp_path, monkeypatch):
    # The same second twice: the unique-name logic must give the second its own name.
    monkeypatch.setattr(automix.export_names, "stamp",
                        lambda _when: "2026-10-21 12-00-00")
    fake = FakeAutomixer()
    full = run(session, tmp_path, fake)
    first = run(session, tmp_path, fake, range=[A, B])
    kept = Path(first["path"]).read_bytes()
    second = run(session, tmp_path, fake, range=[A, B])
    assert len({full["path"], first["path"], second["path"]}) == 3
    assert Path(first["path"]).read_bytes() == kept
    assert Path(full["path"]).is_file()


def test_the_result_carries_the_audio_key_of_the_snapshot_and_the_files_shape(
        session, tmp_path):
    key = export.audio_key(session.state)
    result = run(session, tmp_path, FakeAutomixer(), range=[A, B])
    assert result["edit_key"] == key
    assert result["frames"] == B - A
    assert result["rate"] == RATE


@pytest.mark.parametrize("bad", [[B, A], [A, A], [-5, A], [A], "0-10", [A, "x"],
                                 [0.5, A], [True, A]])
def test_a_bad_range_is_refused_before_anything_is_written(session, tmp_path, bad):
    fake = FakeAutomixer()
    with pytest.raises(automix.AutomixError) as e:
        run(session, tmp_path, fake, range=bad)
    assert e.value.key == "error.automix.bad_range"
    assert fake.calls == []


def test_validate_params_checks_the_range():
    assert automix.validate_range({"range": [A, B]}) == (A, B)
    assert automix.validate_range({}) is None
    assert automix.validate_range({"range": None}) is None
    with pytest.raises(automix.AutomixError):
        automix.validate_range({"range": [B, A]})


def test_a_range_past_the_end_is_cut_at_the_end(session, tmp_path):
    fake = FakeAutomixer()
    result = run(session, tmp_path, fake, range=[A, 100 * RATE])
    end = session.state.length
    assert result["range"] == [A, end]
    assert fake.calls[0]["listing"]["frames"] == end - A


def test_a_plain_ranged_track_export_still_says_where_it_started(session, tmp_path):
    """Only the automixer's manifest is range-relative; "Export all tracks" of a range
    keeps the timeline frame it starts at."""
    args = session.tracks_export_args({"folder": str(tmp_path / "out"), "range": [A, B]})
    done = export.run(session, args)
    listing = json.loads((Path(done["path"]) / "tracks.json").read_text("utf-8"))
    assert listing["start_frame"] == A


def test_session_automix_takes_the_range(session, tmp_path, monkeypatch):
    seen = {}

    def fake_run(_session, params, *_args, **_kwargs):
        seen.update(params)
        raise automix.AutomixError("error.automix.failed", code=1, tail="")

    monkeypatch.setattr(automix, "run", fake_run)
    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(tmp_path / "automixer.json"))
    session.automix({"range": [A, B]})
    deadline = time.monotonic() + 10
    while "range" not in seen and time.monotonic() < deadline:
        time.sleep(0.02)
    assert seen["range"] == [A, B]
    with pytest.raises(automix.AutomixError):
        session.automix({"range": [B, A]})
