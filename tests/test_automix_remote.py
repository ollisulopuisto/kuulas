"""Run the automixer on another Mac: ssh + rsync, with fakes (no network, no real ssh).

The fake ``ssh`` ignores the host and the options and runs its last argument with
``sh -c`` on this machine; the fake ``rsync`` strips a ``host:`` prefix and calls the
real local rsync. Both are passed through the ``ssh_command`` / ``rsync_command``
settings. The fake automixer is the one of ``test_automix``."""

import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest
from test_automix import FAKE, Reports, voice

from kuulas import automix, automix_remote
from kuulas.jobs import JobCancelledError
from kuulas.session import Session

FAKE_SSH = textwrap.dedent('''
    import os, sys
    last = sys.argv[-1]
    if os.environ.get("FAKE_SSH_LOG"):
        with open(os.environ["FAKE_SSH_LOG"], "a") as f:
            f.write(last + "\\n")
    if os.environ.get("FAKE_SSH_DROP") and "--target-lufs" in last:
        print("partial output before the link died", flush=True)
        sys.exit(255)
    if os.environ.get("FAKE_SSH_FAIL"):
        print("ssh: connect to host: Connection refused", flush=True)
        sys.exit(255)
    if os.environ.get("FAKE_SSH_DETACH"):
        # like a remote process that outlives a dead ssh: own session, parent waits
        pid = os.fork()
        if pid == 0:
            os.setsid()
            if "--target-lufs" in last:
                fd = os.open(os.devnull, os.O_WRONLY)
                os.dup2(fd, 1)
                os.dup2(fd, 2)
            os.execvp("sh", ["sh", "-c", last])
        _, status = os.waitpid(pid, 0)
        sys.exit(os.waitstatus_to_exitcode(status))
    os.execvp("sh", ["sh", "-c", last])
''')

FAKE_RSYNC = textwrap.dedent('''
    import os, re, sys
    args, skip = [], False
    for a in sys.argv[1:]:
        if skip:
            skip = False
        elif a == "-e":
            skip = True
        else:
            args.append(re.sub(r"^studio:", "", a))
    os.execvp("rsync", ["rsync", *args])
''')


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    src = tmp_path / "src"
    src.mkdir()
    s.import_media([str(voice(src / "Olli.wav", 3, 1)),
                    str(voice(src / "Maija.wav", 3, 2))])
    yield s
    s.close()


@pytest.fixture
def remote(tmp_path, monkeypatch, session):
    """Remote settings using the fakes; the work folder and the 'remote' cwd are local."""
    ssh = tmp_path / "fake_ssh.py"
    ssh.write_text(FAKE_SSH, encoding="utf-8")
    rsync = tmp_path / "fake_rsync.py"
    rsync.write_text(FAKE_RSYNC, encoding="utf-8")
    script = tmp_path / "fake_automixer.py"
    script.write_text(FAKE, encoding="utf-8")
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "call.json"))
    cwd = tmp_path / "remote cwd"
    cwd.mkdir()
    work = tmp_path / "work"
    return {"remote": {
        "enabled": True, "host": "studio", "cwd": str(cwd), "work_dir": str(work),
        "command": [sys.executable, str(script)],
        "ssh_command": [sys.executable, str(ssh)],
        "rsync_command": [sys.executable, str(rsync)]}, "work": work, "cwd": cwd}


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setattr(automix.tempfile, "tempdir", str(root))
    return root


def do_run(session, settings, cancel=None, extra=None, reports=None):
    reports = reports if reports is not None else Reports()
    if "work" in settings:  # the whole ``remote`` fixture
        settings = {"remote": settings["remote"]}
    if extra:
        settings = {**settings, "extra_args": extra}
    result = automix.run(session, {}, settings, reports, cancel or threading.Event())
    return result, reports


def leftovers(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_a_remote_run_makes_the_same_file_as_a_local_one(
        session, remote, temp_root, tmp_path):
    result, _ = do_run(session, remote)
    final = Path(result["path"])
    assert final.is_file()
    assert final.stat().st_size > 0
    call = json.loads((tmp_path / "call.json").read_text())
    # the tool ran in the remote folder, on the uploaded stems, in the work folder
    assert call["cwd"] == str(remote["cwd"])
    assert call["positional"][0].startswith(str(remote["work"]))
    assert all(call["exists"])
    assert "kuulas-run-" in call["positional"][0]
    assert "--progress" in call["argv"]
    assert leftovers(temp_root) == []
    assert not list(final.parent.glob("*.partial*"))


def test_the_flags_file_comes_back_beside_the_mix(
        session, remote, temp_root, monkeypatch):
    monkeypatch.setenv("FAKE_FLAGS", "12.5 s: check this\n")
    result, _ = do_run(session, remote)
    assert result["flags"] is not None
    flags = Path(result["flags"])
    assert flags.name == Path(result["path"]).stem + " flags.txt"
    assert "check this" in flags.read_text()


def test_progress_has_upload_and_download_steps(session, remote, temp_root):
    _, reports = do_run(session, remote)
    messages = [m for _, m, _ in reports.items]
    assert any(m.startswith("1/6 ") for m in messages)
    assert any(m.startswith("2/6 ") for m in messages)  # upload
    assert any(m.startswith("3/6 ") for m in messages)  # analysis
    assert any(m.startswith("6/6 ") for m in messages)  # download
    fractions = [f for f, _, _ in reports.items]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0
    assert 0.15 < max(f for f, m, _ in reports.items if m.startswith("2/6 ")) <= 0.25
    assert any(0.25 < f < 0.95 for f in fractions)


def test_a_local_run_keeps_four_steps(session, remote, temp_root, tmp_path):
    local = {"command": remote["remote"]["command"], "cwd": str(tmp_path),
             "extra_args": []}
    _, reports = do_run(session, local)
    steps = [m for _, m, _ in reports.items if m[:1].isdigit()]
    assert steps
    assert all(m[1:4] == "/4 " for m in steps)


def test_the_remote_folder_is_removed_after_success(session, remote, temp_root):
    do_run(session, remote)
    assert leftovers(remote["work"]) == []


def test_the_remote_folder_is_removed_after_a_failure(session, remote, temp_root):
    with pytest.raises(automix.AutomixError) as caught:
        do_run(session, remote, extra=["--mode", "fail"])
    assert caught.value.key == "error.automix.failed"
    assert "boom" in caught.value.params["tail"]
    assert leftovers(remote["work"]) == []
    assert leftovers(temp_root) == []


def test_cancel_kills_the_remote_automixer_and_cleans_up(
        session, remote, temp_root, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SSH_DETACH", "1")
    cancel = threading.Event()
    seen: list[BaseException] = []

    def go():
        try:
            do_run(session, remote, cancel, extra=["--mode", "hang"])
        except BaseException as e:  # noqa: BLE001 - recorded for the assertion
            seen.append(e)

    worker = threading.Thread(target=go)
    worker.start()
    deadline = time.monotonic() + 60
    while not (tmp_path / "call.json").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    time.sleep(0.3)
    cancel.set()
    worker.join(timeout=60)
    assert not worker.is_alive()
    assert isinstance(seen[0], JobCancelledError)
    # the (fake) remote process is gone: it was not in ssh's process group
    for _ in range(40):
        alive = subprocess.run(  # noqa: S603
            ["/usr/bin/pgrep", "-f", str(remote["work"])],
            capture_output=True, check=False).returncode == 0
        if not alive:
            break
        time.sleep(0.1)
    assert not alive
    assert leftovers(remote["work"]) == []
    assert leftovers(temp_root) == []


def test_a_lost_connection_is_remote_lost_and_leaves_nothing(
        session, remote, temp_root, monkeypatch):
    monkeypatch.setenv("FAKE_SSH_DROP", "1")
    with pytest.raises(automix.AutomixError) as caught:
        do_run(session, remote)
    assert caught.value.key == "error.automix.remote_lost"
    assert "partial output" in caught.value.params["tail"]
    assert leftovers(remote["work"]) == []
    assert leftovers(temp_root) == []
    folder = Path(session.package.path).parent
    assert not list(folder.glob("*.wav"))
    assert not list(folder.glob("*.partial*"))


def test_an_unreachable_host_fails_cleanly(session, remote, temp_root, monkeypatch):
    monkeypatch.setenv("FAKE_SSH_FAIL", "1")
    with pytest.raises(automix.AutomixError) as caught:
        do_run(session, remote)
    assert caught.value.key == "error.automix.remote_lost"
    assert leftovers(temp_root) == []


@pytest.mark.parametrize("host", ["-oProxyCommand=touch /tmp/x", "a b", "", "a\nb",
                                  "-p", "host;rm", "x:y", "a\tb"])
def test_unsafe_hosts_are_refused(host, session, remote):
    with pytest.raises(automix_remote.RemoteError) as caught:
        automix_remote.check_host(host)
    assert caught.value.key == "error.automix.bad_remote_host"
    bad = {**remote["remote"], "host": host}
    with pytest.raises(automix.AutomixError):
        automix.save_settings({"remote": bad})
    with pytest.raises(automix.AutomixError):
        automix.run(session, {}, {"remote": bad}, Reports(), threading.Event())


@pytest.mark.parametrize("host", ["studio", "me@studio.tail1234.ts.net", "mac-studio"])
def test_good_hosts_pass(host):
    assert automix_remote.check_host(host) == host


@pytest.mark.parametrize("path", ["a b/c", "/x/$(id)", "../x", "/x/../y", "", "/", "a;b"])
def test_unsafe_work_folders_are_refused(path):
    with pytest.raises(automix_remote.RemoteError):
        automix_remote.check_work_dir(path)


def test_quoting_keeps_spaces_quotes_and_substitutions_literal(tmp_path):
    marker = tmp_path / "pwned"
    words = ["printf", "%s|", "a b", "it's", 'say "hi"', f"$(touch {marker})", "~/x y"]
    done = subprocess.run(  # noqa: S603
        ["/bin/sh", "-c", automix_remote.line(words)], capture_output=True,
        text=True, check=True, env={**os.environ, "HOME": "/home/me"})
    assert done.stdout == f"a b|it's|say \"hi\"|$(touch {marker})|/home/me/x y|"
    assert not marker.exists()


def test_a_folder_with_spaces_and_quotes_is_the_working_folder(
        session, remote, temp_root, tmp_path):
    odd = tmp_path / "it's a \"dir\" $HOME"
    odd.mkdir()
    settings = {"remote": {**remote["remote"], "cwd": str(odd)}}
    do_run(session, settings)
    call = json.loads((tmp_path / "call.json").read_text())
    assert call["cwd"] == str(odd)


def test_the_remote_folder_is_removed_only_when_it_is_one_of_ours(
        remote, tmp_path, monkeypatch):
    log = tmp_path / "ssh.log"
    monkeypatch.setenv("FAKE_SSH_LOG", str(log))
    settings = automix_remote.resolve(remote["remote"])
    for bad in ("", "/", "//", "/home/me", "/srv/kuulas-run-xyz",
                "x/kuulas-run-zzzzzzzzzzzz"):
        assert automix_remote.remove_remote(settings, bad) is False
    assert not log.exists()
    victim = remote["work"] / "kuulas-run-0123456789ab"
    victim.mkdir(parents=True)
    assert automix_remote.remove_remote(settings, str(victim)) is True
    assert not victim.exists()


def test_the_log_says_where_it_ran_and_times_the_transfers(session, remote, temp_root):
    result, _ = do_run(session, remote)
    text = Path(result["log_file"]).read_text()
    assert "ran on: studio" in text
    assert "upload: " in text
    assert "download: " in text
    assert "automixer: " in text


def test_a_local_log_does_not_mention_a_remote(session, remote, temp_root, tmp_path):
    local = {"command": remote["remote"]["command"], "cwd": str(tmp_path)}
    result, _ = do_run(session, local)
    text = Path(result["log_file"]).read_text()
    assert "ran on:" not in text
    assert "upload:" not in text


def test_the_capability_probe_goes_through_the_remote_wrapper(
        session, remote, temp_root, monkeypatch):
    automix.clear_capability_cache()
    seen: list[list[str]] = []

    def recording(cmd, cwd, on_line, cancel, stop=None):
        seen.append(list(cmd))
        return automix.run_process(cmd, cwd, on_line, cancel)

    options = {"bed_under_speech_db": -12.0}
    automix.run(session, {"options": options}, {"remote": remote["remote"]}, Reports(),
                threading.Event(), run_process=recording)
    probe = seen[0]
    assert probe[0] == sys.executable
    assert probe[1].endswith("fake_ssh.py")
    assert "BatchMode=yes" in probe
    assert probe[-1].endswith("--help") or "--help" in probe[-1]
    assert "cd " in probe[-1]
    automix.clear_capability_cache()


def test_the_probe_is_cached_per_host_and_folder(remote):
    automix.clear_capability_cache()
    calls: list[str] = []

    def fake(cmd, _cwd, on_line, _cancel):
        calls.append(cmd[-1])
        on_line("--bed-under-speech-db" if "studio" in cmd else "nothing")
        return 0

    one = automix_remote.resolve(remote["remote"])
    two = {**one, "host": "other"}
    a = automix.remote_capabilities(one, run_process=fake)
    b = automix.remote_capabilities(two, run_process=fake)
    again = automix.remote_capabilities(one, run_process=fake)
    assert a == {"bed_under_speech_db": True, "balance_speakers_max_db": False}
    assert b == {"bed_under_speech_db": False, "balance_speakers_max_db": False}
    assert again == a
    assert len(calls) == 2
    automix.clear_capability_cache()


def helper(remote, text):
    """Remote settings whose automixer is a shell that answers --help with ``text``."""
    return {**remote["remote"], "command": ["sh", "-c", f"echo {text}", "x"]}


def test_the_connection_test_reports_each_check(remote):
    gated = {"bed_under_speech_db": "--bed-under-speech-db"}
    result = automix_remote.connection_test(helper(remote, "usage"), gated)
    ids = [c["id"] for c in result["checks"]]
    assert ids[:2] == ["rsync_local", "ssh"]
    assert {"rsync_remote", "disk", "cwd", "command", "flags"} <= set(ids)
    by = {c["id"]: c for c in result["checks"]}
    assert [by[k]["ok"] for k in ("ssh", "cwd", "disk")] == [True, True, True]
    assert by["command"]["ok"] is True
    # an older automixer: reported on its own, the rest still passes
    assert by["flags"]["ok"] is False
    assert by["flags"]["missing"] == ["--bed-under-speech-db"]
    newer = automix_remote.connection_test(
        helper(remote, "usage --bed-under-speech-db"), gated)
    assert newer["ok"] is True
    assert {c["id"]: c for c in newer["checks"]}["flags"]["ok"] is True


def test_the_connection_test_names_a_missing_folder(remote):
    bad = {**remote["remote"], "cwd": str(remote["cwd"] / "nope")}
    result = automix_remote.connection_test(bad, {})
    by = {c["id"]: c for c in result["checks"]}
    assert result["ok"] is False
    assert by["cwd"]["ok"] is False
    assert by["ssh"]["ok"] is True
    assert "command" not in by  # cannot be tried without its folder


def test_the_connection_test_names_a_failing_command(remote):
    bad = {**remote["remote"], "command": ["false"]}
    result = automix_remote.connection_test(bad, {})
    by = {c["id"]: c for c in result["checks"]}
    assert by["cwd"]["ok"] is True
    assert by["command"]["ok"] is False
    assert result["ok"] is False


def test_the_connection_test_stops_at_a_dead_link(remote, monkeypatch):
    monkeypatch.setenv("FAKE_SSH_FAIL", "1")
    result = automix_remote.connection_test(remote["remote"], {})
    by = {c["id"]: c for c in result["checks"]}
    assert by["ssh"]["ok"] is False
    assert "Connection refused" in by["ssh"]["detail"]
    assert "cwd" not in by
    assert result["ok"] is False


def test_the_connection_test_refuses_a_bad_host_without_calling_ssh(
        remote, tmp_path, monkeypatch):
    log = tmp_path / "ssh.log"
    monkeypatch.setenv("FAKE_SSH_LOG", str(log))
    result = automix_remote.connection_test({**remote["remote"], "host": "-oX=y"}, {})
    assert result["ok"] is False
    assert result["checks"][0]["id"] == "settings"
    assert not log.exists()


def test_every_ssh_call_is_non_interactive_and_checks_host_keys(remote):
    argv = automix_remote.ssh_argv(automix_remote.resolve(remote["remote"]), "true")
    joined = " ".join(argv)
    assert "BatchMode=yes" in argv
    assert "ConnectTimeout=8" in argv
    assert "ServerAliveInterval=15" in argv
    assert "ServerAliveCountMax=4" in argv
    assert "StrictHostKeyChecking" not in joined
    assert "UserKnownHostsFile" not in joined
    assert argv[-2:] == ["studio", "true"]
    assert argv[-3] == "--"


def test_remote_plugins_are_listed_by_ssh_find(remote, tmp_path, monkeypatch):
    home = tmp_path / "home"
    vst = home / "Library/Audio/Plug-Ins/VST3"
    (vst / "Vendor").mkdir(parents=True)
    (vst / "Vendor" / "dxRevive.vst3").mkdir()
    (vst / "Other.vst3").mkdir()
    monkeypatch.setenv("HOME", str(home))
    # (this Mac's own /Library plug-ins are found too: only the fake home's are checked)
    found = [p for p in automix_remote.list_plugins(remote["remote"])
             if p["path"].startswith(str(home))]
    assert [p["name"] for p in found] == ["dxRevive", "Other"]
    assert found[0]["path"] == str(vst / "Vendor" / "dxRevive.vst3")
    assert found[0]["format"] == "VST3"


def test_remote_plugin_listing_failure_is_none(remote, monkeypatch):
    monkeypatch.setenv("FAKE_SSH_FAIL", "1")
    assert automix_remote.list_plugins(remote["remote"]) is None


def test_remote_settings_default_to_local_and_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(tmp_path / "automixer.json"))
    resolved = automix.resolve_settings({})
    assert resolved["remote"]["enabled"] is False
    assert resolved["remote"]["command"] == ["uv", "run", "automixer"]
    assert resolved["remote"]["work_dir"] == "~/kuulas-remote"
    assert resolved["remote"]["ssh_command"] == ["ssh"]
    assert resolved["remote"]["rsync_command"] == ["rsync"]
    stored = automix.save_settings({"remote": {
        "enabled": True, "host": "studio", "cwd": "~/podcast"}})
    assert stored["remote"]["host"] == "studio"
    assert automix.resolve_settings(automix.load_settings())["remote"]["enabled"] is True
    # the test hooks survive a save from the dialog, which does not send them
    path = tmp_path / "automixer.json"
    data = json.loads(path.read_text())
    data["remote"]["ssh_command"] = ["myssh"]
    path.write_text(json.dumps(data))
    automix.save_settings({"remote": {"enabled": True, "host": "studio2"}})
    assert automix.resolve_settings(automix.load_settings())["remote"][
        "ssh_command"] == ["myssh"]


def test_a_remote_run_does_not_need_the_local_automixer_folder(
        session, remote, temp_root):
    settings = {"remote": remote["remote"], "cwd": "/no/such/local/folder"}
    result, _ = do_run(session, settings)
    assert Path(result["path"]).is_file()


@pytest.fixture
def client(session, remote, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient  # noqa: PLC0415
    from test_automix_session import IdleEngine  # noqa: PLC0415

    from kuulas.server import create_app  # noqa: PLC0415

    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(tmp_path / "automixer.json"))
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, IdleEngine(), language="en", ui_dir=ui)) as c:
        yield c


def test_the_settings_api_refuses_a_bad_host_and_keeps_a_good_one(client, remote):
    bad = client.put("/api/settings/automixer",
                     json={"remote": {"enabled": True, "host": "-oProxyCommand=x"}})
    assert bad.status_code == 400
    assert bad.json()["error"]["key"] == "error.automix.bad_remote_host"
    good = client.put("/api/settings/automixer", json={"remote": remote["remote"]})
    assert good.status_code == 200
    got = client.get("/api/settings/automixer").json()
    assert got["resolved"]["remote"]["host"] == "studio"
    assert got["resolved"]["remote"]["enabled"] is True


def test_the_test_route_runs_the_checks_with_the_dialogs_fields(client, remote):
    r = client.post("/api/settings/automixer/remote-test",
                    json={"remote": helper(remote, "usage")})
    assert r.status_code == 200
    by = {c["id"]: c for c in r.json()["checks"]}
    assert by["ssh"]["ok"] is True
    assert "flags" in by
    bad = client.post("/api/settings/automixer/remote-test",
                      json={"remote": {**remote["remote"], "host": "a b"}})
    assert bad.json()["ok"] is False
    assert bad.json()["checks"][0]["id"] == "settings"


def test_the_plugins_route_asks_the_remote_mac_and_falls_back(
        client, remote, monkeypatch):
    client.put("/api/settings/automixer", json={"remote": remote["remote"]})
    ok = client.get("/api/plugins").json()
    assert ok["remote"] == "studio"
    assert ok["remote_failed"] is False
    monkeypatch.setenv("FAKE_SSH_FAIL", "1")
    down = client.get("/api/plugins").json()
    assert down["plugins"] == []
    assert down["remote_failed"] is True
