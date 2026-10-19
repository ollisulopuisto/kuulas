"""Slow hold-to-play listening (WP26): Shift+J / Shift+L play slowed down while held.

The engine side is tape-rate play at a signed slow speed and a stop on release,
with a fake device (nothing is played). Stop must leave the playhead where the
audio stopped. The key state machine lives in ui/slow-hold.js.
"""

import pytest
from test_engine import RATE, Clock, install_rig, make

from kuulas import messages
from kuulas.messages import KuulasError
from kuulas.shuttle import DEFAULT_SLOW, SLOW_SPEEDS, slow_hold_speed


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def rig(monkeypatch):
    return install_rig(monkeypatch)


def test_the_slow_speeds_and_default():
    assert SLOW_SPEEDS == (0.25, 0.5, 0.75)
    assert DEFAULT_SLOW == 0.5


@pytest.mark.parametrize("setting", SLOW_SPEEDS)
def test_direction_sets_the_sign(setting):
    assert slow_hold_speed("l", setting) == setting
    assert slow_hold_speed("j", setting) == -setting


def test_an_unknown_setting_falls_back_to_the_default():
    assert slow_hold_speed("l", 0.6) == DEFAULT_SLOW
    assert slow_hold_speed("j", None) == -DEFAULT_SLOW


def test_an_unknown_direction_is_refused():
    with pytest.raises(KuulasError):
        slow_hold_speed("k", 0.5)


@pytest.mark.parametrize("direction", ["l", "j"])
@pytest.mark.parametrize("setting", SLOW_SPEEDS)
def test_stop_leaves_the_playhead_where_the_audio_stopped(rig, direction, setting):
    engine, _, _ = make(rig, Clock())
    start = RATE
    speed = slow_hold_speed(direction, setting)
    engine.play(start, rate=speed, preserve_pitch=False)
    for _ in range(10):
        engine._render(1000)
    engine.stop()
    status = engine.status()
    assert not status["playing"]
    assert abs(status["position"] - (start + 10000 * speed)) <= 1
