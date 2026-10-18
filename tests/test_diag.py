"""Playback diagnostics (--debug): the pure parts and one engine run."""

import pytest
from test_engine import clock, make, rig  # noqa: F401 - the engine fakes and fixtures

from kuulas import cli, diag


@pytest.fixture(autouse=True)
def debug_off():
    diag.disable()
    yield
    diag.disable()


def test_ring_keeps_the_newest_entries_and_never_grows():
    ring = diag.Ring(4)
    for i in range(6):
        ring.push(float(i), float(i) * 2, float(i) * 3)
    assert ring.count == 6
    assert [row[0] for row in ring.since(0)] == [2.0, 3.0, 4.0, 5.0]
    assert [row[0] for row in ring.since(4)] == [4.0, 5.0]
    assert ring.since(6) == []
    assert ring.since(5)[0] == (5.0, 10.0, 15.0)


def test_slow_component_names_the_largest_share():
    assert diag.slow_component(total=30.0, reads=20.0, mix=5.0) == "reads"
    assert diag.slow_component(total=30.0, reads=2.0, mix=25.0) == "mix"
    assert diag.slow_component(total=30.0, reads=2.0, mix=3.0) == "other"


def test_report_line_has_the_numbers_and_the_slow_part():
    line = diag.format_report({
        "block_ms": 21.3, "callbacks": 47, "cb_avg_ms": 3.2, "cb_max_ms": 30.5,
        "late_blocks": 2, "failed_blocks": 0, "device": "Speakers",
        "device_rate": 44100, "resampling": True, "slow": "reads",
        "slowest_reads": [{"name": "a.wav", "ms": 28.0}, {"name": "b.wav", "ms": 4.5}],
    })
    for part in ("21.3", "3.2", "30.5", "late 2", "failed 0", "Speakers", "44100",
                 "resampling", "slow: reads", "a.wav: 28.0", "b.wav: 4.5"):
        assert part in line
    quiet = diag.format_report({
        "block_ms": 21.3, "callbacks": 47, "cb_avg_ms": 3.2, "cb_max_ms": 4.0,
        "late_blocks": 0, "failed_blocks": 0, "device": "Speakers",
        "device_rate": 48000, "resampling": False, "slow": None, "slowest_reads": [],
    })
    assert "slow:" not in quiet
    assert "resampling" not in quiet


def test_raise_line_gives_the_numbers_that_caused_it():
    line = diag.format_raise(old=1024, new=2048, late=2, cb_max_ms=35.0, block_ms=21.3)
    for part in ("1024", "2048", "35.0", "21.3", "2"):
        assert part in line


def test_summary_picks_the_slow_component_of_the_worst_callback():
    probe = diag.Probe()
    probe.callback(total=0.002, reads=0.0005, mix=0.001)
    probe.callback(total=0.040, reads=0.030, mix=0.005)
    probe.mixer_read(0.030, "m1")
    probe.mixer_read(0.001, "m2")
    probe.prefetch_read(0.050, "m3")
    probe.prefetch_read(0.002, "m4")
    s, _ = probe.summary((0, 0, 0), block_ms=21.0, name_of=lambda i: i.upper())
    assert s["callbacks"] == 2
    assert s["cb_max_ms"] == pytest.approx(40.0)
    assert s["slow"] == "reads"
    assert s["prefetch_reads"] == 2
    assert s["prefetch_max_ms"] == pytest.approx(50.0)
    assert [r["name"] for r in s["slowest_reads"]] == ["M3", "M1", "M4"]


def test_summary_has_no_slow_part_while_the_callback_keeps_up():
    probe = diag.Probe()
    probe.callback(total=0.002, reads=0.0005, mix=0.001)
    s, _ = probe.summary((0, 0, 0), block_ms=21.0, name_of=str)
    assert s["slow"] is None


def test_debug_switch_reaches_the_engine_default(rig, clock):  # noqa: F811
    engine, _, _ = make(rig, clock)
    assert "debug" not in engine.status()
    diag.enable()
    engine, _, _ = make(rig, clock)
    assert "debug" in engine.status()


def test_cli_debug_flag_turns_diagnostics_on(monkeypatch):
    monkeypatch.setattr(cli, "open_project", lambda *a, **k: 0)
    assert cli.main(["open", "X.kuulas", "--debug"]) == 0
    assert diag.enabled()


def test_engine_measures_reads_and_mix_only_in_debug(rig, clock):  # noqa: F811
    engine, _, _ = make(rig, clock, debug=True)
    engine.play(0)
    rig.stream.pump()
    rig.stream.pump()
    engine._prefetch()
    d = engine.status()["debug"]
    assert d["callbacks"] == 2
    assert d["cb_avg_ms"] > 0
    assert d["cb_max_ms"] >= d["cb_avg_ms"]
    assert d["reads_max_ms"] >= 0
    assert d["mix_max_ms"] >= 0
    assert d["prefetch_reads"] > 0
    assert d["block_ms"] == pytest.approx(1024 / 48000 * 1000)
    assert d["slowest_reads"]
    assert d["slowest_reads"][0]["name"]
    assert d["device"] == "Fake Out"
    assert d["resampling"] is False
    plain, _, _ = make(rig, clock)
    plain.play(0)
    rig.stream.pump()
    assert "debug" not in plain.status()


def test_engine_prints_one_line_per_report_and_one_when_the_buffer_grows(
        rig, clock, capsys):  # noqa: F811
    engine, _, _ = make(rig, clock, debug=True)
    engine.play(0)
    rig.stream.pump()
    engine._report()
    err = capsys.readouterr().err
    assert len(err.strip().splitlines()) == 1
    assert "Fake Out" in err
    rig.stream.pump(underflow=True)
    rig.stream.pump(underflow=True)
    engine._tick()
    err = capsys.readouterr().err
    assert "2048" in err
    assert len(err.strip().splitlines()) == 1
