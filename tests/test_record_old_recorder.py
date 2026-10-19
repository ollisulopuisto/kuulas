"""An editor talking to an older recorder that outlived the previous editor: idle, it is
asked to exit and a fresh one starts; recording, it is never touched (rule 17)."""

import pytest

from kuulas import record_take as rt
from kuulas.record_session import RecordError, RecordSession
from kuulas.session import Session
from kuulas_recorder import PROTOCOL
from kuulas_recorder.client import PROTOCOL as CLIENT_PROTOCOL


class Fleet:
    """Fake recorders: the old one is running at first; ``spawn`` brings up a new one."""

    def __init__(self, old_state: str):
        self.running = {"protocol": PROTOCOL - 1, "state": old_state, "name": "old"}
        self.log: list[tuple[str, str]] = []

    def connect(self):
        if self.running is None:
            raise ConnectionRefusedError("no recorder")
        return FakeClient(self, self.running)

    def spawn(self):
        self.log.append(("spawn", ""))
        self.running = {"protocol": PROTOCOL, "state": "idle", "name": "new"}


class FakeClient:
    closed = False

    def __init__(self, fleet, rec):
        self.fleet, self.rec = fleet, rec

    def request(self, cmd, timeout=None, **args):
        self.fleet.log.append((self.rec["name"], cmd))
        if cmd == "hello":
            return {"protocol": self.rec["protocol"],
                    "status": {"state": self.rec["state"]}}
        if cmd == "quit":
            self.fleet.running = None
            return {"quitting": True}
        if cmd == "arm":
            if self.rec["protocol"] < PROTOCOL:
                from kuulas_recorder.client import RecorderError  # noqa: PLC0415

                raise RecorderError("unknown_command", "no")
            return {"state": "armed", "armed": {"channels": args["channels"],
                                                "preroll_s": args["preroll_s"]}}
        raise AssertionError(cmd)

    def close(self):
        pass


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Show.kuulas")
    yield s
    s.close()


def editor(session, fleet):
    return RecordSession(session, lambda _m: None, connect=fleet.connect,
                         spawn=fleet.spawn, watch=False)


def test_the_client_knows_the_protocol_the_editor_needs():
    assert CLIENT_PROTOCOL == PROTOCOL
    assert PROTOCOL >= 2  # arm for several channels and channel_failed are version 2


def test_an_idle_old_recorder_is_asked_to_exit_and_a_new_one_started(session):
    fleet = Fleet("idle")
    view = editor(session, fleet).arm(device=None, channels=[1], preroll_s=10)
    assert view["armed"] is True
    assert ("old", "quit") in fleet.log
    assert fleet.log.index(("old", "quit")) < fleet.log.index(("spawn", ""))
    assert fleet.running["name"] == "new"


def test_a_listening_old_recorder_is_replaced_too(session):
    fleet = Fleet("armed")
    editor(session, fleet).arm(device=None, channels=[1], preroll_s=10)
    assert fleet.running["name"] == "new"


def test_a_recording_old_recorder_is_never_touched(session):
    fleet = Fleet("recording")
    with pytest.raises(RecordError) as e:
        editor(session, fleet).arm(device=None, channels=[1], preroll_s=10)
    assert e.value.key == "error.record.old_recorder"
    assert e.value.status == 409
    assert [c for _, c in fleet.log] == ["hello"]  # no quit, no spawn, nothing else
    assert fleet.running["name"] == "old"


def test_a_current_recorder_is_left_alone(session):
    fleet = Fleet("idle")
    fleet.running["protocol"] = PROTOCOL
    editor(session, fleet).arm(device=None, channels=[1], preroll_s=10)
    assert ("old", "quit") not in fleet.log
    assert ("spawn", "") not in fleet.log


def test_the_notice_exists_in_both_catalogs():
    assert "old_recorder" in rt.RECORDER_ERRORS
