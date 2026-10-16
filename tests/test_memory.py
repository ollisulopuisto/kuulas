"""One memory budget for every cache (WP36, ground rule 15)."""

import logging

import numpy as np
import pytest

from kuulas import caches, messages
from kuulas.memory import MemoryBudget


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


def block(n_bytes: int, fill: float = 0.0) -> np.ndarray:
    return np.full(n_bytes // 4, fill, dtype=np.float32)


def test_eviction_respects_the_budget_and_drops_the_least_recently_used():
    b = MemoryBudget(limit_bytes=1000)
    for i in range(10):
        b.put("x", f"k{i}", block(400))
        assert b.used <= 1000
    assert b.get("x", "k9") is not None
    assert b.get("x", "k0") is None  # evicted, not spilled: gone


def test_a_hit_protects_an_entry_from_eviction():
    b = MemoryBudget(limit_bytes=1000)
    b.put("x", "a", block(400))
    b.put("x", "b", block(400))
    assert b.get("x", "a") is not None  # a is now the most recent
    b.put("x", "c", block(400))
    assert b.get("x", "a") is not None
    assert b.get("x", "b") is None


def test_an_entry_larger_than_the_budget_is_not_kept():
    b = MemoryBudget(limit_bytes=100)
    b.put("x", "big", block(400))
    assert b.used == 0
    assert b.get("x", "big") is None


def test_evicted_arrays_spill_to_disk_and_come_back(tmp_path):
    b = MemoryBudget(limit_bytes=1000)
    spill_a, spill_b = tmp_path / "a.npy", tmp_path / "b.npy"
    b.put("env", "a", block(800, 1.0), spill=spill_a)
    b.put("env", "b", block(800, 2.0), spill=spill_b)  # pushes a out
    assert spill_a.exists()
    assert b.used <= 1000
    again = b.get("env", "a", spill=spill_a)
    assert again is not None
    assert float(again[0]) == 1.0
    assert b.stats()["env"]["disk_hits"] == 1


def test_spilling_never_leaves_a_half_written_file(tmp_path):
    b = MemoryBudget(limit_bytes=500)
    b.put("env", "a", block(400), spill=tmp_path / "a.npy")
    b.put("env", "b", block(400), spill=tmp_path / "b.npy")
    assert not list(tmp_path.glob("*.partial"))


def test_a_corrupt_spill_file_is_a_miss_not_an_error(tmp_path):
    spill = tmp_path / "a.npy"
    spill.write_bytes(b"not numpy")
    b = MemoryBudget(limit_bytes=1000)
    assert b.get("env", "a", spill=spill) is None


def test_fetch_computes_once_then_hits():
    b = MemoryBudget(limit_bytes=10_000)
    calls = []

    def compute():
        calls.append(1)
        return block(400)

    b.fetch("x", "k", compute)
    b.fetch("x", "k", compute)
    b.fetch("x", "k", compute)
    assert len(calls) == 1
    s = b.stats()["x"]
    assert (s["hits"], s["misses"]) == (2, 1)
    assert s["hit_rate"] == pytest.approx(2 / 3)


def test_shrinking_the_limit_evicts_at_once():
    b = MemoryBudget(limit_bytes=10_000)
    for i in range(10):
        b.put("x", f"k{i}", block(800))
    b.set_limit(1600)
    assert b.used <= 1600


def test_default_budget_is_2_gb():
    assert MemoryBudget().limit == 2 * 1024**3


def test_hit_rates_are_logged_in_the_ui_language(caplog):
    b = MemoryBudget(limit_bytes=10_000)
    b.fetch("peaks", "k", lambda: block(40))
    b.fetch("peaks", "k", lambda: block(40))
    with caplog.at_level(logging.INFO, logger="kuulas.memory"):
        b.log_stats()
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "peaks" in text
    assert "50%" in text
    messages.set_language("fi")
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="kuulas.memory"):
        b.log_stats()
    assert "välimuisti" in "\n".join(r.getMessage() for r in caplog.records).lower()


def test_a_key_that_cannot_be_computed_fails_closed():
    with pytest.raises(caches.CacheKeyError):
        caches.key([None], {}, "peaks@1")
    with pytest.raises(caches.CacheKeyError):
        caches.key([""], {}, "peaks@1")
    with pytest.raises(caches.CacheKeyError):
        caches.key(["abc"], {"x": object()}, "peaks@1")
    with pytest.raises(caches.CacheKeyError):
        caches.key(["abc"], {}, "no-version")
    assert caches.key(["abc"], {}, "peaks@1")
