"""Windowed short-term loudness per track and for the mix (WP49)."""

import threading
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from speechmix.meter import IntegratedMeter

from kuulas import loudness_curve
from kuulas.engine import Engine
from kuulas.server import create_app
from kuulas.session import Session

RATE = 8000


def tone_lufs(seconds: float, lufs: float, rate: int = RATE) -> np.ndarray:
    """Mono 1 kHz sine whose BS.1770 loudness is ``lufs`` (K-weighting is
    ~0 dB at 1 kHz, and a sine's mean square is amp^2 / 2)."""
    t = np.arange(round(seconds * rate)) / rate
    amp = 10 ** ((lufs + 3.01) / 20)
    return (amp * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)[None, :]


def reader(audio: np.ndarray, calls: list | None = None):
    def read(first: int, count: int) -> np.ndarray:
        if calls is not None:
            calls.append(count)
        out = np.zeros((audio.shape[0], count), dtype=np.float32)
        lo, hi = max(0, first), min(audio.shape[1], first + count)
        if hi > lo:
            out[:, lo - first:hi - first] = audio[:, lo:hi]
        return out
    return read


def test_constant_tone_reads_its_level_in_every_window():
    audio = tone_lufs(20, -23.0)
    m = loudness_curve.measure(reader(audio), audio.shape[1], RATE)
    assert len(m.curve) == 18  # 3 s windows, 1 s hop: (20 - 3) / 1 + 1
    times = [t for t, _ in m.curve]
    assert times[0] == pytest.approx(1.5)  # a window's time is its centre
    assert np.diff(times) == pytest.approx(1.0)
    assert all(abs(v - -23.0) < 0.2 for _, v in m.curve)
    assert m.integrated == pytest.approx(-23.0, abs=0.2)


def test_a_step_in_level_shows_in_the_curve():
    audio = np.concatenate([tone_lufs(10, -30.0), tone_lufs(10, -20.0)], axis=1)
    m = loudness_curve.measure(reader(audio), audio.shape[1], RATE)
    by_time = dict(m.curve)
    assert by_time[2.5] == pytest.approx(-30.0, abs=0.3)
    assert by_time[17.5] == pytest.approx(-20.0, abs=0.3)
    assert -30.0 < by_time[10.5] < -20.0  # the window straddling the step


def test_silence_is_floored_not_minus_infinity():
    audio = np.zeros((1, 5 * RATE), dtype=np.float32)
    m = loudness_curve.measure(reader(audio), audio.shape[1], RATE)
    assert all(v == -70.0 for _, v in m.curve)
    assert m.integrated is None


def test_shorter_than_one_window_gives_no_curve():
    audio = tone_lufs(2, -23.0)
    m = loudness_curve.measure(reader(audio), audio.shape[1], RATE)
    assert m.curve == []


def test_reads_in_chunks_of_chunk_sec_and_matches_one_shot():
    # CHUNK_SEC went from 60 to 15 s (docs/MEMORY.md): the reads follow it.
    audio = tone_lufs(150, -25.0) * np.linspace(0.5, 1.0, 150 * RATE, dtype=np.float32)
    calls: list[int] = []
    m = loudness_curve.measure(reader(audio, calls), audio.shape[1], RATE)
    assert max(calls) <= loudness_curve.CHUNK_SEC * RATE
    assert len(calls) == -(-150 // loudness_curve.CHUNK_SEC)
    whole = IntegratedMeter(RATE)
    whole.add(audio)
    assert m.integrated == pytest.approx(whole.value(), abs=0.01)
    assert m.curve[0][1] == pytest.approx(float(whole.short_term()[0]), abs=0.01)


def test_true_peak_of_a_full_scale_sine_is_about_zero_dbtp():
    audio = tone_lufs(5, -10.0)
    audio = audio / np.abs(audio).max()
    m = loudness_curve.measure(reader(audio), audio.shape[1], RATE)
    assert m.true_peak_db == pytest.approx(0.0, abs=0.3)


# -- the session ----------------------------------------------------------


def wav(path: Path, lufs: float, seconds: float = 8.0, rate: int = 48000) -> Path:
    sf.write(path, tone_lufs(seconds, lufs, rate)[0], rate, subtype="FLOAT")
    return path


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "C.kuulas")
    s.import_media([str(wav(tmp_path / "a.wav", -30.0)),
                    str(wav(tmp_path / "b.wav", -20.0))])
    yield s
    s.close()


def test_session_curves_per_track_and_mix(session):
    out = session.loudness_curve()
    assert [t["track_id"] for t in out["tracks"]] == [t.id for t in session.state.tracks]
    levels = [t["curve"][0][1] for t in out["tracks"]]
    assert levels[0] == pytest.approx(-30.0, abs=0.5)
    assert levels[1] == pytest.approx(-20.0, abs=0.5)
    assert out["mix"]["curve"]
    assert out["mix"]["integrated"] is not None
    assert out["mix"]["true_peak_db"] < 0.0


def spy_reads(session, monkeypatch):
    calls = []
    real = session.store.read

    def read(*a, **k):
        calls.append(a)
        return real(*a, **k)

    monkeypatch.setattr(session.store, "read", read)
    return calls


def test_second_call_comes_from_the_cache(session, monkeypatch):
    first = session.loudness_curve()
    calls = spy_reads(session, monkeypatch)
    assert session.loudness_curve() == first
    assert calls == []


def test_cache_key_follows_content_not_names_or_targets(session, monkeypatch):
    session.loudness_curve()
    track = session.state.tracks[0].id
    session.edit("set_track", {"track_id": track, "name": "Renamed",
                               "target_lufs": -21.0})
    calls = spy_reads(session, monkeypatch)
    session.loudness_curve()
    assert calls == []


def test_a_gain_change_recomputes_that_track_and_the_mix(session, monkeypatch):
    before = session.loudness_curve()
    track = session.state.tracks[0].id
    session.edit("set_track", {"track_id": track, "gain_db": 6.0})
    calls = spy_reads(session, monkeypatch)
    after = session.loudness_curve()
    assert calls  # something was measured again
    assert after["tracks"][0]["curve"][0][1] == pytest.approx(
        before["tracks"][0]["curve"][0][1] + 6.0, abs=0.3)
    assert after["tracks"][1]["curve"] == before["tracks"][1]["curve"]


def test_a_missing_cache_is_recomputed(session):
    first = session.loudness_curve()
    for f in (session.package.path / "caches" / "analysis").glob("*.json"):
        f.unlink()
    assert session.loudness_curve() == first


def test_the_session_lock_is_free_while_measuring(session, monkeypatch):
    free = []
    real = session.store.read

    def read(*a, **k):
        def probe():
            got = session.lock.acquire(timeout=1.0)
            if got:
                session.lock.release()
            free.append(got)
        th = threading.Thread(target=probe)
        th.start()
        th.join()
        return real(*a, **k)

    monkeypatch.setattr(session.store, "read", read)
    session.loudness_curve()
    assert free
    assert all(free)


def test_route(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    client = TestClient(create_app(session, Engine(session), language="en", ui_dir=ui))
    body = client.get("/api/loudness-curve").json()
    assert len(body["tracks"]) == 2
    assert "true_peak_db" in body["mix"]


def test_each_track_reports_its_target_own_or_role_default(session):
    first, second = session.state.tracks
    session.edit("set_track", {"track_id": first.id, "target_lufs": -21.0})
    session.edit("set_track", {"track_id": second.id, "kind": "music"})
    out = session.loudness_curve()
    assert out["tracks"][0]["target_lufs"] == -21.0  # the track's own
    assert out["tracks"][1]["target_lufs"] == -23.0  # music role default


def test_a_new_target_shows_without_a_remeasure(session, monkeypatch):
    session.loudness_curve()
    session.edit("set_track", {"track_id": session.state.tracks[0].id,
                               "target_lufs": -30.0})
    calls = spy_reads(session, monkeypatch)
    assert session.loudness_curve()["tracks"][0]["target_lufs"] == -30.0
    assert calls == []
