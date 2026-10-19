"""File > Locate media… (WP39 UI): point at a folder, relink by SHA-256, say what
was found and what is still missing."""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas.messages import KuulasError
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


def wav(path: Path, seed: int, seconds: float = 1.0) -> Path:
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32),
             RATE, subtype="PCM_16")
    return path


@pytest.fixture(autouse=True)
def _private_media_prefs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Talk.kuulas")
    yield s
    s.close()


def lose(session, tmp_path, names=("a.wav", "b.wav")):
    """Import files, then move them into a folder the project does not know."""
    sources = [wav(tmp_path / n, i + 1) for i, n in enumerate(names)]
    session.import_media([str(p) for p in sources])
    ids = [session.store.find(p) for p in sources]
    elsewhere = tmp_path / "elsewhere" / "deep"
    elsewhere.mkdir(parents=True)
    for p in sources:
        p.rename(elsewhere / ("renamed-" + p.name))
    return ids, elsewhere.parent


def test_status_lists_missing_media_with_names(session, tmp_path):
    ids, _ = lose(session, tmp_path)
    status = session.media_status()
    assert [m["id"] for m in status["missing"]] == sorted(ids)
    assert {m["name"] for m in status["missing"]} == {"a.wav", "b.wav"}
    assert all(m["size"] > 0 for m in status["missing"])


def test_locate_reports_found_and_still_missing(session, tmp_path):
    ids, folder = lose(session, tmp_path)
    (folder / "deep" / "renamed-b.wav").unlink()
    report = session.locate_media(str(folder))
    assert [f["id"] for f in report["found"]] == [ids[0]]
    assert report["found"][0]["path"].endswith("renamed-a.wav")
    assert [m["id"] for m in report["still_missing"]] == [ids[1]]
    assert session.store.missing() == [ids[1]]


def test_locate_never_accepts_a_same_size_file_with_other_content(session, tmp_path):
    ids, folder = lose(session, tmp_path, names=("a.wav",))
    (folder / "deep" / "renamed-a.wav").unlink()
    wav(folder / "impostor.wav", seed=99)  # same length, different bytes
    report = session.locate_media(str(folder))
    assert report["found"] == []
    assert [m["id"] for m in report["still_missing"]] == ids


def test_locate_commits_nothing(session, tmp_path):
    _ids, folder = lose(session, tmp_path)
    nodes = session.history.nodes()
    session.locate_media(str(folder))
    assert session.history.nodes() == nodes


def test_locate_refuses_a_folder_that_is_not_there(session, tmp_path):
    lose(session, tmp_path)
    with pytest.raises(KuulasError) as caught:
        session.locate_media(str(tmp_path / "nope"))
    assert caught.value.key == "error.locate.no_folder"


def test_locate_with_nothing_missing_is_a_quiet_report(session, tmp_path):
    session.import_media([str(wav(tmp_path / "a.wav", 1))])
    report = session.locate_media(str(tmp_path))
    assert report == {"found": [], "still_missing": [], "partial": []}


@pytest.fixture
def client(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()

    class Engine:
        def status(self):
            return {"playing": False, "position": 0, "until": None, "notices": []}

        def close(self):
            pass

    with TestClient(create_app(session, Engine(), language="en", ui_dir=ui)) as c:
        yield c


def test_api_status_and_locate(client, session, tmp_path):
    ids, folder = lose(session, tmp_path)
    status = client.get("/api/media/status").json()
    assert [m["id"] for m in status["missing"]] == sorted(ids)
    answer = client.post("/api/media/locate", json={"folder": str(folder)})
    assert answer.status_code == 200
    body = answer.json()
    assert {f["id"] for f in body["found"]} == set(ids)
    assert body["still_missing"] == []
    assert client.get("/api/state").json()["missing"] == []


def test_api_locate_bad_folder_is_400(client, session, tmp_path):
    lose(session, tmp_path)
    answer = client.post("/api/media/locate", json={"folder": str(tmp_path / "nope")})
    assert answer.status_code == 400
    assert answer.json()["error"]["key"] == "error.locate.no_folder"
    answer = client.post("/api/media/locate", json={})
    assert answer.status_code == 400
