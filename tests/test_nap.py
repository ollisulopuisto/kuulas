"""App Nap cooperation (nap.py): an NSProcessInfo activity brackets each
in-process job so a hidden editor window is not throttled mid-export."""

from __future__ import annotations

import pytest

from kuulas import nap


class FakeProcessInfo:
    """Stands in for NSProcessInfo: records begin/end pairs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def beginActivityWithOptions_reason_(self, options, reason):  # noqa: N802 - pyobjc name
        self.calls.append(("begin", (options, reason)))
        return ("token", len(self.calls))

    def endActivity_(self, token):  # noqa: N802 - pyobjc name
        self.calls.append(("end", token))


def test_hold_brackets_the_work_on_macos():
    pi = FakeProcessInfo()
    with nap.hold("export mix", platform="darwin", process_info=pi):
        (kind, payload), = pi.calls
        assert kind == "begin"
        options, reason = payload
        assert options == nap.NS_ACTIVITY_USER_INITIATED_ALLOWING_IDLE_SYSTEM_SLEEP
        assert reason == "export mix"
    assert pi.calls[1] == ("end", ("token", 1))


def test_hold_signals_user_work_without_preventing_idle_sleep():
    pi = FakeProcessInfo()
    with nap.hold("export mix", platform="darwin", process_info=pi):
        [(kind, payload)] = pi.calls
        assert kind == "begin"
        options, reason = payload
        # NSActivityUserInitiatedAllowingIdleSystemSleep from NSProcessInfo.h.
        # Unlike NSActivityBackground, this keeps user work out of App Nap; unlike
        # NSActivityUserInitiated, it leaves the idle-system-sleep bit clear.
        assert options == 0x00EFFFFF
        assert options & (1 << 20) == 0  # NSActivityIdleSystemSleepDisabled
        assert options & (1 << 40) == 0  # NSActivityIdleDisplaySleepDisabled
        assert reason == "export mix"


def test_hold_releases_when_the_work_raises():
    pi = FakeProcessInfo()
    with pytest.raises(RuntimeError), nap.hold("job", platform="darwin",
                                               process_info=pi):
        raise RuntimeError("boom")
    assert [kind for kind, _ in pi.calls] == ["begin", "end"]


def test_hold_is_a_noop_off_macos():
    pi = FakeProcessInfo()
    with nap.hold("job", platform="linux", process_info=pi):
        pass
    with nap.hold("job", platform="win32", process_info=pi):
        pass
    assert pi.calls == []


def test_hold_is_a_noop_without_pyobjc():
    # process_info=None is what hold() resolves when Foundation is missing.
    with nap.hold("job", platform="darwin", process_info=None):
        pass


def test_hold_survives_a_begin_failure():
    class ObjectiveCError(Exception):
        pass

    class Broken:
        def beginActivityWithOptions_reason_(self, options, reason):  # noqa: N802 - pyobjc name
            raise ObjectiveCError

    # A failed assertion must never take the job down with it.
    with nap.hold("job", platform="darwin", process_info=Broken()):
        pass
