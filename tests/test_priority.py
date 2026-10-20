"""The playback-priority gate (docs/PLAYBACK-PRIORITY.md): pure, fake clocks."""

import threading

import pytest

from kuulas import priority


class Clock:
    """A fake monotonic clock; ``sleep`` advances it and runs a hook."""

    def __init__(self):
        self.now = 100.0
        self.slept = 0.0
        self.on_sleep = None

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        self.slept += seconds
        if self.on_sleep is not None:
            self.on_sleep(self)


def make(playing=False):
    clock = Clock()
    state = {"playing": playing}
    gate = priority.PlaybackGate(clock=clock, sleep=clock.sleep)
    gate.watch(lambda: state["playing"])
    return gate, clock, state


def test_without_a_source_nothing_is_playing():
    clock = Clock()
    gate = priority.PlaybackGate(clock=clock, sleep=clock.sleep)
    assert not gate.is_playing()
    assert not gate.interactive()


def test_follows_the_engine_and_holds_one_second_after_it_stops():
    gate, clock, state = make(playing=True)
    assert gate.is_playing()
    state["playing"] = False
    assert gate.is_playing()  # held: a stop/start must not let a chunk in
    clock.now += priority.HOLD_S - 0.01
    assert gate.is_playing()
    clock.now += 0.02
    assert not gate.is_playing()


def test_input_while_playing_and_scrub_hold_one_second():
    gate, clock, state = make()
    gate.note_input()
    assert not gate.is_playing()  # input alone, stopped: no pause
    assert gate.interactive()      # but at most one worker
    clock.now += priority.INTERACTIVE_S + 0.01
    assert not gate.interactive()
    gate.note_input(scrub=True)
    assert gate.is_playing()
    clock.now += priority.HOLD_S + 0.01
    assert not gate.is_playing()
    state["playing"] = True
    gate.note_input()
    state["playing"] = False
    clock.now += priority.HOLD_S - 0.01
    assert gate.is_playing()


def test_a_failing_source_counts_as_not_playing():
    clock = Clock()
    gate = priority.PlaybackGate(clock=clock, sleep=clock.sleep)

    def broken():
        raise RuntimeError("engine closed")

    gate.watch(broken)
    assert not gate.is_playing()


def test_wait_while_playing_blocks_until_stop_and_reports_pause():
    gate, clock, state = make(playing=True)
    events = []

    def stop_later(c):
        if c.slept >= 0.5:
            state["playing"] = False

    clock.on_sleep = stop_later
    ok = gate.wait_while_playing(None, on_pause=lambda: events.append("pause"),
                                 on_resume=lambda: events.append("resume"))
    assert ok
    assert events == ["pause", "resume"]
    # stopped at 0.5 s, then the 1 s hold
    assert clock.slept == pytest.approx(0.5 + priority.HOLD_S, abs=2 * priority.POLL_S)


def test_wait_while_playing_returns_at_once_when_stopped():
    gate, clock, _ = make()
    events = []
    assert gate.wait_while_playing(None, on_pause=lambda: events.append("pause"))
    assert clock.slept == 0
    assert events == []


def test_cancel_ends_a_wait():
    gate, clock, _ = make(playing=True)
    cancel = threading.Event()

    def cancel_later(c):
        if c.slept >= 0.3:
            cancel.set()

    clock.on_sleep = cancel_later
    assert gate.wait_while_playing(cancel) is False
    assert clock.slept < 0.5


def test_checkpoint_pauses_only_background_threads():
    gate, clock, state = make(playing=True)
    clock.on_sleep = lambda c: state.update(playing=c.slept < 0.2)
    priority.checkpoint(gate=gate)  # a request thread: never waits
    assert clock.slept == 0
    with priority.background():
        events = []
        with priority.listening(lambda: events.append("p"), lambda: events.append("r")):
            priority.checkpoint(gate=gate)
        assert events == ["p", "r"]
    assert clock.slept > 0
    assert not priority.is_background()


def test_background_is_inherited_by_gated_map_workers():
    gate, _, _ = make()
    seen = []
    with priority.background():
        priority.gated_map(lambda _x: seen.append(priority.is_background()), [1, 2, 3],
                           max_workers=2, gate=gate)
    assert seen == [True, True, True]
    seen.clear()
    priority.gated_map(lambda _x: seen.append(priority.is_background()), [1, 2],
                       max_workers=2, gate=gate)
    assert seen == [False, False]


def test_gated_map_keeps_order_and_raises_the_first_error():
    gate, _, _ = make()
    assert priority.gated_map(lambda x: x * 2, [3, 1, 2], max_workers=3,
                              gate=gate) == [6, 2, 4]
    with pytest.raises(ZeroDivisionError):
        priority.gated_map(lambda x: 1 / x, [1, 0, 2], max_workers=2, gate=gate)


def test_gated_map_holds_one_worker_while_interactive():
    clock = Clock()  # never moves: the input stays recent for the whole test
    gate = priority.PlaybackGate(clock=clock,
                                 sleep=lambda _s: threading.Event().wait(0.001))
    gate.watch(lambda: False)
    gate.note_input()
    lock = threading.Lock()
    live = {"now": 0, "most": 0}
    release = threading.Event()

    def work(_x):
        with lock:
            live["now"] += 1
            live["most"] = max(live["most"], live["now"])
        release.wait(0.02)
        with lock:
            live["now"] -= 1

    priority.gated_map(work, range(6), max_workers=4, gate=gate)
    assert live["most"] == 1


def test_gated_map_starts_no_new_item_while_playing_in_the_background():
    gate, clock, state = make()
    started = []

    def work(x):
        started.append(x)
        if x == 0:
            state["playing"] = True  # playback starts during the first item

    def stop_later(c):
        if c.slept >= 0.3:
            state["playing"] = False

    clock.on_sleep = stop_later
    with priority.background():
        priority.gated_map(work, [0, 1], max_workers=1, gate=gate)
    assert started == [0, 1]
    assert clock.slept >= 0.3  # item 1 waited for the stop


def test_gated_map_cancel_while_paused_starts_nothing_more():
    gate, clock, _ = make(playing=True)
    cancel = threading.Event()
    clock.on_sleep = lambda c: cancel.set() if c.slept >= 0.2 else None
    started = []
    with priority.background(), pytest.raises(priority.CancelledError):
        priority.gated_map(started.append, [1, 2, 3], max_workers=2, gate=gate,
                           cancel=cancel)
    assert started == []


def test_lowering_a_thread_never_raises():
    done = []

    def run():
        priority.lower_this_thread()
        done.append(True)

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    assert done == [True]
