"""POST/GET /api/profile (the performance report) and /api/log-level, through the
TestClient. The profiler's clock and sleep are fakes, so a "30 second" recording takes
no time; nothing is revealed in Finder."""

import threading

import pytest
from fastapi.testclient import TestClient
from test_server import FakeEngine

from kuulas import logsetup, messages, profiler
from kuulas.server import create_app
from kuulas.session import Session


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Private Talk About Dad.kuulas")
    yield s
    s.close()


def fake_profiler(tmp_path, **kw):
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds

    args = {"out_dir": tmp_path / "logs", "clock": lambda: now[0], "sleep": sleep,
            "reveal": lambda _p: None, "background": False,
            "usage": lambda: (1.0, 0.0), "rss": lambda: (1.0e9, 2.0e9)}
    args.update(kw)
    return profiler.Profiler(**args)


@pytest.fixture
def prof(tmp_path):
    return fake_profiler(tmp_path)


@pytest.fixture
def client(session, prof, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    app = create_app(session, FakeEngine(), language="en", ui_dir=ui, profiler=prof)
    with TestClient(app) as c:
        yield c


def test_status_is_idle_at_first(client):
    r = client.get("/api/profile")
    assert r.status_code == 200
    assert r.json()["state"] == "idle"


def test_start_records_and_the_report_has_the_project_numbers(client, tmp_path):
    r = client.post("/api/profile", json={"action": "start", "seconds": 10})
    assert r.status_code == 202
    status = client.get("/api/profile").json()
    assert status["state"] == "done"
    assert status["samples"] > 400  # 10 s at 20 ms
    (report,) = (tmp_path / "logs").glob("performance-*.txt")
    text = report.read_text(encoding="utf-8")
    assert "Tracks: 0" in text
    assert "Clips: 0" in text
    assert "Late blocks" in text


def test_the_report_names_no_project(client, tmp_path):
    client.post("/api/profile", json={"action": "start", "seconds": 1})
    (report,) = (tmp_path / "logs").glob("performance-*.txt")
    assert "Private Talk" not in report.read_text(encoding="utf-8")
    assert "Private Talk" not in str(client.get("/api/profile").json())


def test_the_default_span_is_thirty_seconds(client):
    client.post("/api/profile", json={"action": "start"})
    assert client.get("/api/profile").json()["seconds"] == 30.0


@pytest.mark.parametrize("seconds", [0, -1, 100000])
def test_bad_spans_are_a_400(client, seconds):
    r = client.post("/api/profile", json={"action": "start", "seconds": seconds})
    assert r.status_code == 400
    assert client.get("/api/profile").json()["state"] == "idle"


def test_a_span_that_is_not_a_number_is_a_400(client):
    r = client.post("/api/profile", json={"action": "start", "seconds": "x"})
    assert r.status_code == 400


def test_unknown_action_is_a_400(client):
    assert client.post("/api/profile", json={"action": "explode"}).status_code == 400


def test_a_second_start_while_running_is_a_409(session, tmp_path):
    gate = threading.Event()
    prof = fake_profiler(tmp_path, sleep=lambda _s: gate.wait(5), background=True)
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, FakeEngine(), language="en", ui_dir=ui,
                               profiler=prof)) as c:
        try:
            assert c.post("/api/profile", json={"action": "start", "seconds": 60}
                          ).status_code == 202
            assert c.get("/api/profile").json()["state"] == "running"
            r = c.post("/api/profile", json={"action": "start", "seconds": 60})
            assert r.status_code == 409
            assert r.json()["error"]["key"] == "error.profile.busy"
        finally:
            c.post("/api/profile", json={"action": "stop"})
            gate.set()
            prof.join(5)
    assert prof.status()["state"] == "done"


def test_stop_when_idle_is_harmless(client):
    r = client.post("/api/profile", json={"action": "stop"})
    assert r.status_code == 200
    assert r.json()["state"] == "idle"


def test_the_profile_endpoint_does_not_hold_the_session_lock(client, session):
    # A recording that took the lock would deadlock this thread: it holds it itself.
    with session.lock:
        r = client.get("/api/profile")
    assert r.status_code == 200


def test_a_page_on_another_site_cannot_start_a_recording(client):
    r = client.post("/api/profile", json={"action": "start", "seconds": 5},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.get("/api/profile").json()["state"] == "idle"


def test_a_foreign_host_header_is_refused(client):
    r = client.get("/api/profile", headers={"Host": "evil.example"})
    assert r.status_code == 400


# -- the log level --------------------------------------------------------------


@pytest.fixture
def settings(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("KUULAS_SETTINGS_FILE", str(path))
    monkeypatch.delenv("KUULAS_LOG_LEVEL", raising=False)
    return path


def test_log_level_reports_the_level_and_the_choices(client, settings):
    body = client.get("/api/log-level").json()
    assert body["levels"] == ["DEBUG", "INFO", "WARNING"]
    assert body["setting"] is None
    assert body["level"] in body["levels"]


def test_log_level_can_be_changed_and_is_remembered(client, settings):
    import logging  # noqa: PLC0415

    root = logging.getLogger()
    before = root.level
    try:
        r = client.post("/api/log-level", json={"level": "debug"})
        assert r.status_code == 200
        assert r.json()["level"] == "DEBUG"
        assert logging.getLogger().level == logging.DEBUG
        assert logsetup.level_setting() == "DEBUG"
        assert client.get("/api/log-level").json()["setting"] == "DEBUG"
    finally:
        root.setLevel(before)


def test_log_level_refuses_what_it_does_not_offer(client, settings):
    r = client.post("/api/log-level", json={"level": "LOUD"})
    assert r.status_code == 400
    assert logsetup.level_setting() is None


def test_log_level_post_is_guarded_like_the_rest(client, settings):
    r = client.post("/api/log-level", json={"level": "DEBUG"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
