"""Tests for import placement options (WP34 / WP46 wiring)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import messages
from kuulas.messages import KuulasError
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


class FakeEngine:
    def __init__(self):
        self.calls: list[tuple] = []
        self.position = 0
        self.playing = False
        self.until = None
        self.notices: list[dict] = []

    def status(self):
        return {
            "playing": self.playing,
            "position": self.position,
            "until": self.until,
            "notices": list(self.notices),
        }

    def close(self):
        self.calls.append(("close",))


def make_wav(path: Path, seconds: float = 1.0, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    sf.write(
        path,
        (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32),
        RATE,
        subtype="PCM_16",
    )
    return path


def test_default_import_is_identical_to_baseline(tmp_path):
    f_a = str(make_wav(tmp_path / "a.wav", seconds=1.0, seed=1))
    f_b = str(make_wav(tmp_path / "b.wav", seconds=1.5, seed=2))

    s1 = Session(tmp_path / "Baseline.kuulas")
    s1.import_media([f_a, f_b], track_per_file=True)

    s2 = Session(tmp_path / "WithOptions.kuulas")
    s2.import_media(
        [f_a, f_b],
        mode=None,
        order="given",
        track_naming="file",
        start_frame=0,
    )

    p1 = s1.state
    p2 = s2.state

    # Same number of tracks
    assert len(p1.tracks) == len(p2.tracks)
    for t1, t2 in zip(p1.tracks, p2.tracks, strict=True):
        assert t1.name == t2.name
        assert t1.kind == t2.kind
        assert len(t1.clips) == len(t2.clips)
        for c1, c2 in zip(t1.clips, t2.clips, strict=True):
            assert c1.start == c2.start
            assert c1.offset == c2.offset
            assert c1.length == c2.length

    # Same sync group structure
    assert len(p1.sync_groups) == len(p2.sync_groups)
    if p1.sync_groups:
        g1, g2 = p1.sync_groups[0], p2.sync_groups[0]
        assert p1.media_item(g1.main).name == p2.media_item(g2.main).name
        assert len(g1.members) == len(g2.members)

    s1.close()
    s2.close()


def test_sequential_mode_places_files_one_after_another(tmp_path):
    f_a = str(make_wav(tmp_path / "intro.wav", seconds=1.0, seed=1))
    f_b = str(make_wav(tmp_path / "body.wav", seconds=1.5, seed=2))

    s = Session(tmp_path / "Sequential.kuulas")
    s.import_media([f_a, f_b], mode="sequential", start_frame=100)

    p = s.state
    assert len(p.tracks) == 1
    t = p.tracks[0]
    assert t.name == "intro"
    assert len(t.clips) == 2

    # First clip starts at start_frame (100)
    c1 = t.clips[0]
    assert c1.start == 100
    assert c1.length == RATE

    # Second clip starts immediately after first
    c2 = t.clips[1]
    assert c2.start == 100 + RATE
    assert c2.length == round(1.5 * RATE)

    # Sequential does not create a sync group
    assert len(p.sync_groups) == 0
    s.close()


def test_order_by_name_natural_sorts(tmp_path):
    f10 = str(make_wav(tmp_path / "take10.wav", seconds=1.0, seed=1))
    f2 = str(make_wav(tmp_path / "take2.wav", seconds=1.0, seed=2))

    s = Session(tmp_path / "OrderName.kuulas")
    s.import_media([f10, f2], mode="side_by_side", order="name")

    p = s.state
    assert len(p.tracks) == 2
    # take2 naturally sorts before take10
    assert p.tracks[0].name == "take2"
    assert p.tracks[1].name == "take10"

    # First placed clip is main in sync group
    assert len(p.sync_groups) == 1
    main_media = p.sync_groups[0].main
    assert p.media_item(main_media).name == "take2.wav"
    s.close()


def test_track_naming_person(tmp_path):
    f_a = str(make_wav(tmp_path / "mic1.wav", seconds=1.0, seed=1))

    s = Session(tmp_path / "PersonName.kuulas")
    # First import a dummy file to assign person Anna
    s.import_media([f_a])
    m_id = s.state.media[0].id
    anna_id = s.create_person("Anna")
    s.set_media_person(m_id, anna_id)

    # Re-import same media (now with person attached in project)
    # with track_naming="person"
    s.import_media([f_a], track_naming="person")
    # Latest track is named after the person
    assert s.state.tracks[-1].name == "Anna"
    s.close()


def test_start_frame_shifts_placement(tmp_path):
    f_a = str(make_wav(tmp_path / "a.wav", seconds=1.0, seed=1))
    f_b = str(make_wav(tmp_path / "b.wav", seconds=1.0, seed=2))

    s = Session(tmp_path / "StartFrame.kuulas")
    s.import_media([f_a, f_b], mode="side_by_side", start_frame=5000)

    p = s.state
    assert p.tracks[0].clips[0].start == 5000
    assert p.tracks[1].clips[0].start == 5000
    s.close()


def test_invalid_import_options_raise_kuulas_error(tmp_path):
    f_a = str(make_wav(tmp_path / "a.wav", seconds=1.0, seed=1))
    s = Session(tmp_path / "Invalid.kuulas")

    with pytest.raises(KuulasError) as exc_mode:
        s.import_media([f_a], mode="unsupported")
    assert exc_mode.value.key == "error.import_plan.bad_mode"

    with pytest.raises(KuulasError) as exc_order:
        s.import_media([f_a], order="unsupported")
    assert exc_order.value.key == "error.import_plan.bad_order"

    with pytest.raises(KuulasError) as exc_naming:
        s.import_media([f_a], track_naming="unsupported")
    assert exc_naming.value.key == "error.import_plan.bad_track_naming"

    s.close()


def test_import_with_options_is_one_undo_step(tmp_path):
    f_a = str(make_wav(tmp_path / "a.wav", seconds=1.0, seed=1))
    f_b = str(make_wav(tmp_path / "b.wav", seconds=1.0, seed=2))

    s = Session(tmp_path / "Undo.kuulas")
    head_before = s.history.head
    s.import_media([f_a, f_b], mode="sequential", start_frame=100)

    assert len(s.state.tracks) == 1
    s.undo()
    assert len(s.state.tracks) == 0
    assert s.history.head == head_before
    s.close()


def test_api_import_options_and_validation(tmp_path):
    f_a = str(make_wav(tmp_path / "a.wav", seconds=1.0, seed=1))
    f_b = str(make_wav(tmp_path / "b.wav", seconds=1.0, seed=2))

    s = Session(tmp_path / "ApiImport.kuulas")
    engine = FakeEngine()
    ui = tmp_path / "ui"
    ui.mkdir()
    app = create_app(s, engine, language="en", ui_dir=ui)
    client = TestClient(app)

    # Valid sequential import
    resp = client.post(
        "/api/import",
        json={"paths": [f_a, f_b], "mode": "sequential", "start_frame": 200},
    )
    assert resp.status_code == 200
    p = resp.json()["project"]
    assert len(p["tracks"]) == 1
    assert p["tracks"][0]["clips"][0]["start"] == 200

    # Invalid mode returns 400 with translated error
    resp_bad = client.post(
        "/api/import",
        json={"paths": [f_a], "mode": "bad_mode"},
    )
    assert resp_bad.status_code == 400
    err = resp_bad.json()
    assert err["error"]["key"] == "error.import_plan.bad_mode"
    assert "text" in err["error"]
    s.close()


def test_api_upload_options_and_validation(tmp_path):
    f_a = make_wav(tmp_path / "up_a.wav", seconds=1.0, seed=1)
    f_b = make_wav(tmp_path / "up_b.wav", seconds=1.0, seed=2)

    s = Session(tmp_path / "ApiUpload.kuulas")
    engine = FakeEngine()
    ui = tmp_path / "ui"
    ui.mkdir()
    app = create_app(s, engine, language="en", ui_dir=ui)
    client = TestClient(app)

    # Valid sequential upload with form data
    with f_a.open("rb") as fa, f_b.open("rb") as fb:
        resp = client.post(
            "/api/upload",
            files=[
                ("files", ("up_a.wav", fa, "audio/wav")),
                ("files", ("up_b.wav", fb, "audio/wav")),
            ],
            data={"mode": "sequential", "start_frame": "300"},
        )
    assert resp.status_code == 200
    p = resp.json()["project"]
    assert len(p["tracks"]) == 1
    assert p["tracks"][0]["clips"][0]["start"] == 300

    # Bad order returns 400
    with f_a.open("rb") as fa:
        resp_bad = client.post(
            "/api/upload",
            files=[("files", ("up_a.wav", fa, "audio/wav"))],
            data={"order": "bad_order"},
        )
    assert resp_bad.status_code == 400
    assert resp_bad.json()["error"]["key"] == "error.import_plan.bad_order"
    s.close()
