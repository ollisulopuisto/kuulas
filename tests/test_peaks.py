"""Peak pyramid and tiles (WP36): computed once at import, keyed by content."""

import logging

import numpy as np
import pytest
import soundfile as sf

from kuulas import caches, messages, peaks
from kuulas.media import MediaStore
from kuulas.memory import MemoryBudget

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


def noise_wav(path, seconds=3.0, channels=1, seed=0):
    rng = np.random.default_rng(seed)
    n = round(seconds * RATE)
    shape = (n,) if channels == 1 else (n, channels)
    sf.write(path, (rng.standard_normal(shape) * 0.1).astype(np.float32), RATE,
             subtype="PCM_16")
    return path


def direct(mono: np.ndarray, per: int) -> np.ndarray:
    """Min/max per ``per`` frames by the plain definition (tail padded with 0)."""
    n = int(np.ceil(mono.shape[0] / per))
    padded = np.zeros(n * per, dtype=np.float32)
    padded[: mono.shape[0]] = mono
    blocks = padded.reshape(n, per)
    return np.stack([blocks.min(axis=1), blocks.max(axis=1)], axis=1)


def test_levels_are_the_documented_ones():
    assert peaks.LEVELS == (256, 1024, 4096, 16384, 65536)


@pytest.mark.parametrize("level", peaks.LEVELS)
def test_every_level_equals_a_direct_min_max(tmp_path, level):
    src = noise_wav(tmp_path / "a.wav", seconds=3.3)  # not a multiple of any level
    store = MediaStore(tmp_path / "media", rate=RATE)
    media = store.import_file(src)
    mono = store.read(media.id, 0, media.frames)[0]
    np.testing.assert_array_equal(store.pyramid(media.id)[level], direct(mono, level))


def test_stereo_peaks_are_of_the_channel_mean(tmp_path):
    src = noise_wav(tmp_path / "s.wav", channels=2)
    store = MediaStore(tmp_path / "media", rate=RATE)
    media = store.import_file(src)
    mono = store.read(media.id, 0, media.frames).mean(axis=0)
    np.testing.assert_allclose(store.pyramid(media.id)[4096], direct(mono, 4096),
                               atol=1e-6)


def test_import_writes_the_pyramid_into_caches_peaks(tmp_path):
    store = MediaStore(tmp_path / "media", rate=RATE)
    media = store.import_file(noise_wav(tmp_path / "a.wav"))
    key = peaks.pyramid_key(store.meta(media.id)["sha256"], RATE)
    assert caches.path(tmp_path / "caches", "peaks", key, "npz").exists()


def test_pyramid_rebuilds_when_deleted_and_says_so(tmp_path, caplog):
    store = MediaStore(tmp_path / "media", rate=RATE, budget=MemoryBudget())
    media = store.import_file(noise_wav(tmp_path / "a.wav"))
    want = store.pyramid(media.id)
    for f in (tmp_path / "caches" / "peaks").iterdir():
        f.unlink()
    fresh = MediaStore(tmp_path / "media", rate=RATE, budget=MemoryBudget())
    with caplog.at_level(logging.INFO, logger="kuulas.media"):
        got = fresh.pyramid(media.id)
    for level in peaks.LEVELS:
        np.testing.assert_array_equal(got[level], want[level])
    assert any("pyramid" in r.getMessage() for r in caplog.records)
    assert any(f.suffix == ".npz" for f in (tmp_path / "caches" / "peaks").iterdir())


def test_tile_is_little_endian_float32_min_max_pairs(tmp_path):
    store = MediaStore(tmp_path / "media", rate=RATE)
    media = store.import_file(noise_wav(tmp_path / "a.wav", seconds=3.3))
    body, _etag = store.peak_tile(media.id, 256, 0)
    got = np.frombuffer(body, dtype="<f4").reshape(-1, 2)
    want = store.pyramid(media.id)[256][: peaks.TILE_PEAKS]
    np.testing.assert_array_equal(got, want)


def test_tiles_cover_the_level_exactly_and_the_last_is_short(tmp_path):
    store = MediaStore(tmp_path / "media", rate=RATE)
    media = store.import_file(noise_wav(tmp_path / "a.wav", seconds=30))
    level = store.pyramid(media.id)[256]
    count = peaks.tile_count(level.shape[0])
    assert count == -(-level.shape[0] // peaks.TILE_PEAKS) > 1
    joined = b"".join(store.peak_tile(media.id, 256, i)[0] for i in range(count))
    np.testing.assert_array_equal(np.frombuffer(joined, "<f4").reshape(-1, 2), level)


def test_etag_is_stable_per_content_and_differs_per_tile_and_level(tmp_path):
    a = MediaStore(tmp_path / "a" / "media", rate=RATE)
    b = MediaStore(tmp_path / "b" / "media", rate=RATE)
    src = noise_wav(tmp_path / "x.wav", seconds=30)
    ma, mb = a.import_file(src), b.import_file(src)
    e = a.peak_tile(ma.id, 256, 0)[1]
    assert e == b.peak_tile(mb.id, 256, 0)[1]  # same bytes, any project, same tag
    assert e != a.peak_tile(ma.id, 256, 1)[1]
    assert e != a.peak_tile(ma.id, 1024, 0)[1]
    other = b.import_file(noise_wav(tmp_path / "y.wav", seed=5))
    assert e != b.peak_tile(other.id, 256, 0)[1]
    assert e.startswith('"')
    assert e.endswith('"')


def test_etag_includes_the_algorithm_version(tmp_path, monkeypatch):
    store = MediaStore(tmp_path / "media", rate=RATE)
    media = store.import_file(noise_wav(tmp_path / "a.wav"))
    before = store.peak_tile(media.id, 256, 0)[1]
    monkeypatch.setattr(peaks, "ALGORITHM", "peaks-pyramid@999")
    assert store.peak_tile(media.id, 256, 0)[1] != before


def test_unknown_level_or_tile_is_refused(tmp_path):
    store = MediaStore(tmp_path / "media", rate=RATE)
    media = store.import_file(noise_wav(tmp_path / "a.wav"))
    with pytest.raises(peaks.PeakError) as e:
        store.peak_tile(media.id, 300, 0)
    assert str(e.value)
    with pytest.raises(peaks.PeakError):
        store.peak_tile(media.id, 256, 9999)
    with pytest.raises(peaks.PeakError):
        store.peak_tile(media.id, 256, -1)


def test_a_missing_linked_file_draws_flat_and_is_not_cached(tmp_path):
    src = noise_wav(tmp_path / "a.wav")
    store = MediaStore(tmp_path / "media", rate=RATE)
    media = store.import_file(src)  # linked
    for f in (tmp_path / "caches" / "peaks").iterdir():
        f.unlink()
    src.unlink()
    fresh = MediaStore(tmp_path / "media", rate=RATE)
    flat = fresh.pyramid(media.id)
    assert not flat[256].any()
    assert not any((tmp_path / "caches" / "peaks").iterdir())
