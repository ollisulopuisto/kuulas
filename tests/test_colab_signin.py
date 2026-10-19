"""Signing in to Google for Colab: the cheap check, the login process with a fake tool,
and the guards. No network, no browser, no real credentials."""

import json
import sys
import textwrap
import time

import pytest
from fastapi.testclient import TestClient

from kuulas import colab_signin, messages
from kuulas.server import create_app
from kuulas.session import Session

#: A stand-in for ``colab-transcribe --login``: prints the address, reads one line (the
#: code)
#: from stdin and, when it is the expected one, writes the token file like the real tool.
FAKE_LOGIN = textwrap.dedent('''
    import json, os, sys
    mode = os.environ.get("FAKE_LOGIN", "ok")
    if "--login" not in sys.argv:
        sys.exit(3)
    print("To authorize, visit this URL in any browser:", flush=True)
    print("  https://accounts.google.com/o/oauth2/auth?x=1", flush=True)
    if mode == "crash":
        print("boom", flush=True)
        sys.exit(1)
    code = sys.stdin.readline().strip()
    if code != "good-code":
        print("bad code", flush=True)
        sys.exit(1)
    with open(os.environ["KUULAS_COLAB_TOKEN"], "w") as f:
        json.dump({"refresh_token": "r", "token": "t"}, f)
''')


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def token(tmp_path, monkeypatch):
    path = tmp_path / "creds" / "token.json"
    path.parent.mkdir()
    monkeypatch.setenv("KUULAS_COLAB_TOKEN", str(path))
    return path


@pytest.fixture
def opened(monkeypatch):
    urls = []
    monkeypatch.setattr(colab_signin, "open_url", urls.append)
    return urls


@pytest.fixture
def tool(tmp_path):
    script = tmp_path / "fake_login.py"
    script.write_text(FAKE_LOGIN, encoding="utf-8")
    return [sys.executable, str(script)]


def wait_for(flow, states, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = flow.status()
        if status["state"] in states:
            return status
        time.sleep(0.02)
    raise AssertionError(f"still {flow.status()['state']}")


def wait_url(flow, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if flow.status()["url"]:
            return flow.status()
        time.sleep(0.02)
    raise AssertionError("no address")


# -- the check -----------------------------------------------------------------


def test_not_signed_in_without_a_token_file(token):
    assert colab_signin.signed_in() is False


def test_signed_in_with_a_token_that_can_be_refreshed(token):
    token.write_text(json.dumps({"refresh_token": "r", "token": "t"}))
    assert colab_signin.signed_in() is True


@pytest.mark.parametrize("text", ["", "not json", "[]", '{"token": "t"}',
                                  '{"refresh_token": ""}'])
def test_a_damaged_or_unusable_token_is_not_signed_in(token, text):
    token.write_text(text)
    assert colab_signin.signed_in() is False


# -- the login process -----------------------------------------------------------------


def test_login_shows_the_address_opens_it_and_signs_in_with_the_code(token, tool, opened):
    flow = colab_signin.SigninFlow()
    flow.start(tool, None)
    status = wait_url(flow)
    assert status["url"] == "https://accounts.google.com/o/oauth2/auth?x=1"
    assert opened == [status["url"]]
    assert status["state"] == "running"
    flow.submit_code("good-code")
    status = wait_for(flow, {"done", "failed"})
    assert status["state"] == "done"
    assert status["signed_in"] is True


def test_a_wrong_code_fails_with_the_tools_last_lines(token, tool, opened):
    flow = colab_signin.SigninFlow()
    flow.start(tool, None)
    wait_url(flow)
    flow.submit_code("nope")
    status = wait_for(flow, {"done", "failed"})
    assert status["state"] == "failed"
    assert "bad code" in status["error"]["text"]
    assert status["signed_in"] is False


def test_the_code_is_never_kept_in_the_status_or_the_log(token, tool, opened, caplog):
    flow = colab_signin.SigninFlow()
    flow.start(tool, None)
    wait_url(flow)
    with caplog.at_level("DEBUG"):
        flow.submit_code("good-code")
        status = wait_for(flow, {"done", "failed"})
    assert "good-code" not in json.dumps(status)
    assert "good-code" not in caplog.text


def test_a_tool_that_exits_without_signing_in_is_a_failure(
        token, tool, opened, monkeypatch):
    monkeypatch.setenv("FAKE_LOGIN", "crash")
    flow = colab_signin.SigninFlow()
    flow.start(tool, None)
    status = wait_for(flow, {"done", "failed"})
    assert status["state"] == "failed"
    assert "boom" in status["error"]["text"]


def test_a_missing_tool_says_so(token, opened):
    flow = colab_signin.SigninFlow()
    flow.start(["no-such-colab-tool-xyz"], None)
    status = wait_for(flow, {"failed"})
    assert status["error"]["key"] == "error.colab.not_found"


def test_cancel_stops_the_login(token, tool, opened):
    flow = colab_signin.SigninFlow()
    flow.start(tool, None)
    wait_url(flow)
    flow.cancel()
    assert wait_for(flow, {"cancelled"})["state"] == "cancelled"


@pytest.mark.parametrize("code", ["", "   ", "a b", "x\ny", "z" * 2000])
def test_a_code_with_a_wrong_shape_is_refused(token, tool, opened, code):
    flow = colab_signin.SigninFlow()
    flow.start(tool, None)
    wait_url(flow)
    with pytest.raises(colab_signin.SigninError):
        flow.submit_code(code)
    flow.cancel()


def test_a_second_start_while_running_keeps_the_first(token, tool, opened):
    flow = colab_signin.SigninFlow()
    flow.start(tool, None)
    wait_url(flow)
    flow.start(tool, None)
    assert flow.status()["state"] == "running"
    flow.cancel()


# -- the API and the guard ---------------------------------------------------------


class Engine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


@pytest.fixture
def client(tmp_path, token, opened, tool, monkeypatch):
    settings = tmp_path / "colab.json"
    settings.write_text(json.dumps({"command": tool}))
    monkeypatch.setenv("KUULAS_COLAB_FILE", str(settings))
    session = Session(tmp_path / "P.kuulas")
    app = create_app(session, Engine(), language="en", ui_dir=tmp_path)
    with TestClient(app) as c:
        yield c
    session.close()


def test_the_api_signs_in_and_reports_each_step(client, token):
    first = client.get("/api/colab/signin").json()
    assert first["signed_in"] is False
    assert first["state"] == "idle"
    assert client.post("/api/colab/signin").status_code == 202
    deadline = time.monotonic() + 10
    while not client.get("/api/colab/signin").json()["url"]:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    sent = client.post("/api/colab/signin/code", json={"code": "good-code"})
    assert sent.status_code == 200
    while client.get("/api/colab/signin").json()["state"] == "running":
        assert time.monotonic() < deadline
        time.sleep(0.02)
    done = client.get("/api/colab/signin").json()
    assert done["state"] == "done"
    assert done["signed_in"] is True


def test_a_code_with_no_login_running_is_refused(client):
    response = client.post("/api/colab/signin/code", json={"code": "abc"})
    assert response.status_code == 400


def test_transcribing_on_colab_needs_the_sign_in_first(client, token):
    response = client.post("/api/transcribe",
                           json={"media_ids": ["m"], "backend": "colab"})
    assert response.status_code == 409
    assert response.json()["error"]["key"] == "error.colab.not_signed_in"
