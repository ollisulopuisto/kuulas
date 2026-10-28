"""The export adapter preserves a global master and rolls back every partial file."""

import errno
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf
from speechmix import programme

from kuulas import export, priority
from kuulas.session import Session

RATE = 48000
RESULT = SimpleNamespace(boost_db=1.25, lufs=-16.0, cost_lu=0.1, reached=True)


@pytest.fixture(autouse=True)
def candidate_streaming(monkeypatch):
    """Candidate path is tested explicitly, not enabled in production yet."""
    monkeypatch.setattr(export, "STREAM_MASTERING_ENABLED", True)


@pytest.fixture
def source():
    # A fractional final block and unequal channels reveal interleaving mistakes.
    rng = np.random.default_rng(20261028)
    return (rng.normal(size=(2, 24013)) * np.array([[0.06], [0.03]])).astype(
        np.float32)


@pytest.fixture
def streaming_api(monkeypatch):
    # Until speechmix's new API lands these tests exercise the agreed contract.
    def install(implementation):
        if not hasattr(export.programme, "master_scratch_bytes"):
            monkeypatch.setattr(export.programme, "master_scratch_bytes",
                                lambda frames: 40 * frames, raising=False)
        monkeypatch.setattr(export.programme, "master_stream", implementation,
                            raising=False)

    return install


def adapter(tmp_path, source, cancel=None, tick=None):
    target = tmp_path / "mix.wav"
    scratch = []
    blocks = []
    result = export._mastered(
        SimpleNamespace(frames=source.shape[1], rate=RATE),
        SimpleNamespace(write=lambda block: blocks.append(block.copy())), 2,
        lambda start, count: source[:, start:start + count], -16.0, 1,
        cancel, tick or (lambda _: None), target, scratch)
    return result, blocks, scratch


def test_stream_adapter_rereads_exact_source_and_writes_bounded_blocks(
        tmp_path, source, streaming_api, monkeypatch):
    calls = []

    def master_stream(read, write, frames, channels, rate, target, *, check,
                      scratch_dir, **_kwargs):
        assert (frames, channels, rate, target) == (source.shape[1], 2, RATE, -16.0)
        assert Path(scratch_dir) == tmp_path
        # Dry attempts can reread in either order without changing the source.
        for start, stop in ((100, 301), (0, 513), (20000, frames), (0, frames)):
            check()
            block = read(start, stop)
            assert block.dtype == np.float32
            np.testing.assert_array_equal(block, source[:, start:stop])
        for start in range(0, frames, 4096):
            check()
            write(read(start, min(start + 4096, frames)).astype(np.float64) * 0.5)
        calls.append(True)
        return RESULT

    streaming_api(master_stream)
    monkeypatch.setattr(export, "BLOCK_SECONDS", 0.1)
    monkeypatch.setattr(export.programme, "master",
                        lambda *_: pytest.fail("whole master"))
    seen = []
    result, blocks, scratch = adapter(tmp_path, source, tick=seen.append)
    assert calls == [True]
    assert result == {"boost_db": 1.25, "lufs": -16.0, "cost_lu": 0.1, "reached": True}
    assert max(block.shape[1] for block in blocks) <= 4096
    assert all(block.dtype == np.float32 for block in blocks)
    np.testing.assert_array_equal(np.concatenate(blocks, axis=1), source * 0.5)
    assert seen == sorted(seen)
    assert seen[-1] == 1.0
    assert scratch == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("mode", ["cancel", "priority", "disk", "algorithm"])
@pytest.mark.parametrize("after_write", [False, True])
def test_stream_failure_rolls_back_spool_and_sink(
        tmp_path, source, streaming_api, monkeypatch, mode, after_write):
    path = tmp_path / "input.wav"
    sf.write(path, source.T, RATE, subtype="FLOAT")
    session = Session(tmp_path / "test.kuulas")
    session.import_media([str(path)])
    out = tmp_path / "out"
    stop = threading.Event()
    finished = []

    def master_stream(read, write, frames, channels, rate, target, *, check,
                      scratch_dir, **_kwargs):
        assert read(0, min(512, frames)).shape == (channels, min(512, frames))
        if after_write:
            write(read(0, min(512, frames)).astype(np.float64))
        if mode == "cancel":
            stop.set()
            check()
        elif mode == "priority":
            def cancelled(_cancel):
                raise priority.CancelledError
            monkeypatch.setattr(priority, "checkpoint", cancelled)
            check()
        elif mode == "disk":
            raise OSError(errno.ENOSPC, "full during mastering")
        else:
            raise ValueError("mastering failed")
        pytest.fail("cancel did not stop the master")

    streaming_api(master_stream)
    try:
        expected = ValueError if mode == "algorithm" else export.ExportError
        with pytest.raises(expected) as error:
            session.export({"folder": str(out), "kind": "mix", "format": "wav",
                            "master_lufs": -16.0}, cancel=stop,
                           progress=lambda fraction, _message: finished.append(fraction))
        if mode != "algorithm":
            key = ("error.export.cannot_write" if mode == "disk"
                   else "error.export.cancelled")
            assert error.value.key == key
        assert list(out.rglob("*")) == []
        assert session.history.checkpoints() == []
        assert not finished or finished[-1] < 1.0
    finally:
        session.close()


def test_cancel_after_render_does_not_start_master(tmp_path, source, streaming_api):
    stop = threading.Event()
    streaming_api(lambda *_args, **_kwargs: pytest.fail("started after cancellation"))

    def tick(fraction):
        if fraction >= 0.6:
            stop.set()

    with pytest.raises(export._Cancel):
        adapter(tmp_path, source, cancel=stop, tick=tick)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not hasattr(programme, "master_stream"),
                    reason="requires new optional speechmix streaming API")
@pytest.mark.parametrize("channels", [1, 2])
def test_real_stream_adapter_matches_whole_programme(tmp_path, channels, monkeypatch):
    """Output conversion and block boundaries must preserve the old master's audio."""
    rng = np.random.default_rng(7301)
    source = (rng.normal(size=(channels, 96013)) * 0.035).astype(np.float32)
    source[:, 4095:4098] = np.array([0.85, -0.9, 0.8])
    expected, expected_result = export.programme.master(source, RATE, -16.0)
    real_stream = export.programme.master_stream

    def bounded(*args, **kwargs):
        return real_stream(*args, block_frames=4096, **kwargs)

    monkeypatch.setattr(export.programme, "master_stream", bounded)
    blocks = []
    scratch = []
    result = export._mastered(
        SimpleNamespace(frames=source.shape[1], rate=RATE),
        SimpleNamespace(write=lambda block: blocks.append(block.copy())), channels,
        lambda start, count: source[:, start:start + count], -16.0, 1,
        None, lambda _: None, tmp_path / "mix.wav", scratch)
    actual = np.concatenate(blocks, axis=1)
    np.testing.assert_allclose(actual, expected.astype(np.float32), rtol=0, atol=1e-7)
    assert result["boost_db"] == expected_result.boost_db
    assert result["lufs"] == pytest.approx(expected_result.lufs, abs=1e-8)
    assert result["cost_lu"] == expected_result.cost_lu
    assert result["reached"] == expected_result.reached
    assert scratch == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not hasattr(programme, "master_stream"),
                    reason="requires new optional speechmix streaming API")
@pytest.mark.parametrize("phase", ["analysis", "output"])
def test_real_stream_cancellation_cleans_private_scratch(
        tmp_path, source, monkeypatch, phase):
    stop = threading.Event()
    real_stream = export.programme.master_stream
    checks = 0
    blocks = []

    def wrapped(*args, check, **kwargs):
        def cancel_during_analysis():
            nonlocal checks
            checks += 1
            if phase == "analysis" and checks == 2:
                stop.set()
            check()
        return real_stream(*args, check=cancel_during_analysis,
                           block_frames=4096, **kwargs)

    def write(block):
        blocks.append(block.copy())
        if phase == "output":
            stop.set()

    monkeypatch.setattr(export.programme, "master_stream", wrapped)
    scratch = []
    with pytest.raises(export._Cancel):
        export._mastered(
            SimpleNamespace(frames=source.shape[1], rate=RATE),
            SimpleNamespace(write=write), 2,
            lambda start, count: source[:, start:start + count], -16.0, 1,
            stop, lambda _: None, tmp_path / "mix.wav", scratch)
    assert bool(blocks) == (phase == "output")
    assert scratch == []
    assert list(tmp_path.iterdir()) == []


def test_real_stream_full_disk_in_output_rolls_back(tmp_path, source, monkeypatch):
    path = tmp_path / "input.wav"
    sf.write(path, source.T, RATE, subtype="FLOAT")
    session = Session(tmp_path / "test.kuulas")
    session.import_media([str(path)])
    out = tmp_path / "out"

    def full(_self, _block):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(export._WavWriter, "write", full)
    try:
        with pytest.raises(export.ExportError) as error:
            session.export({"folder": str(out), "kind": "mix", "format": "wav",
                            "master_lufs": -16.0})
        assert error.value.key == "error.export.cannot_write"
        assert list(out.rglob("*")) == []
        assert session.history.checkpoints() == []
    finally:
        session.close()


@pytest.mark.skipif(not hasattr(programme, "master_stream"),
                    reason="requires new optional speechmix streaming API")
def test_render_failure_closes_and_removes_master_source(tmp_path, source):
    def failed(_first, _count):
        raise ValueError("renderer failed")

    scratch = []
    with pytest.raises(ValueError, match="renderer failed"):
        export._mastered(
            SimpleNamespace(frames=source.shape[1], rate=RATE),
            SimpleNamespace(write=lambda _block: None), 2, failed, -16.0, 1,
            None, lambda _: None, tmp_path / "mix.wav", scratch)
    assert scratch == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not hasattr(programme, "master_scratch_bytes"),
                    reason="requires new optional speechmix scratch API")
def test_disk_preflight_covers_api_source_output_and_margin():
    frames, channels = 90 * 60 * RATE, 2
    expected = (export.programme.master_scratch_bytes(frames)
                + frames * channels * 4 * 3 + 64 * 1024**2)
    assert export._master_disk_bytes(frames, channels) == expected


def test_insufficient_disk_fails_before_render_or_master(
        tmp_path, source, streaming_api, monkeypatch):
    streaming_api(lambda *_args, **_kwargs: pytest.fail("master started"))
    needed = export._master_disk_bytes(source.shape[1], 2)
    monkeypatch.setattr(export.shutil, "disk_usage",
                        lambda _: SimpleNamespace(free=needed - 1))
    streaming_api(lambda *_args, **_kwargs: pytest.fail("master started"))
    scratch = []
    with pytest.raises(OSError, match="No space left") as error:
        export._mastered(
            SimpleNamespace(frames=source.shape[1], rate=RATE),
            SimpleNamespace(write=lambda _block: pytest.fail("sink written")), 2,
            lambda *_args: pytest.fail("render started"), -16.0, 1,
            None, lambda _: None, tmp_path / "mix.wav", scratch)
    assert error.value.errno == errno.ENOSPC
    assert scratch == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not hasattr(programme, "master_stream"),
                    reason="requires new optional speechmix streaming API")
def test_disk_shortage_is_reported_as_export_error(tmp_path, source, monkeypatch):
    path = tmp_path / "input.wav"
    sf.write(path, source.T, RATE, subtype="FLOAT")
    session = Session(tmp_path / "test.kuulas")
    session.import_media([str(path)])
    out = tmp_path / "out"
    monkeypatch.setattr(export.shutil, "disk_usage", lambda _: SimpleNamespace(free=1))
    try:
        with pytest.raises(export.ExportError) as error:
            session.export({"folder": str(out), "kind": "mix", "format": "wav",
                            "master_lufs": -16.0})
        assert error.value.key == "error.export.cannot_write"
        assert list(out.rglob("*")) == []
        assert session.history.checkpoints() == []
    finally:
        session.close()


@pytest.mark.parametrize("missing", ["master_stream", "master_scratch_bytes", "both"])
def test_older_speechmix_keeps_existing_mastering(tmp_path, source, monkeypatch, missing):
    """Either missing capability falls back to the original global master."""
    source = np.tile(source, (1, 4))
    expected, reference = export.programme.master(source, RATE, -16.0)
    for name in ("master_stream", "master_scratch_bytes"):
        if missing in (name, "both"):
            monkeypatch.delattr(export.programme, name, raising=False)
    result, blocks, scratch = adapter(tmp_path, source)
    np.testing.assert_array_equal(np.concatenate(blocks, axis=1),
                                  expected.astype(np.float32))
    assert result["boost_db"] == reference.boost_db
    assert result["lufs"] == reference.lufs
    assert result["cost_lu"] == reference.cost_lu
    assert result["reached"] == reference.reached
    assert scratch == []
    assert list(tmp_path.iterdir()) == []


def test_streaming_remains_disabled_until_acceptance(tmp_path, source, monkeypatch):
    monkeypatch.setattr(export, "STREAM_MASTERING_ENABLED", False)
    monkeypatch.setattr(export.programme, "master_stream",
                        lambda *_args, **_kwargs: pytest.fail("unaccepted streaming"),
                        raising=False)
    result, _blocks, scratch = adapter(tmp_path, source)
    assert result["boost_db"] == 0.0  # sub-second reference skips target search
    assert scratch == []
