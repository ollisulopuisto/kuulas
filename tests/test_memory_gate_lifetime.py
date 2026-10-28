"""Per-key computation gates leave no locks behind after their callers finish."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from kuulas.memory import MemoryBudget



def test_distinct_failed_computations_release_their_gates():
    budget = MemoryBudget(1024)

    def fail():
        raise ValueError('failed computation')
    for key in range(1000):
        with pytest.raises(ValueError, match='failed computation'):
            budget.fetch('failure', str(key), fail)
    assert budget._computing == {}
    assert budget.used == 0


def test_success_after_failure_is_cached_and_releases_the_gate():
    budget = MemoryBudget(1024)
    with pytest.raises(ZeroDivisionError):
        budget.fetch('x', 'key', lambda: 1 / 0)
    value = np.ones(4, dtype=np.float32)
    assert budget.fetch('x', 'key', lambda: value) is value
    assert budget.get('x', 'key') is value
    assert budget._computing == {}


def test_spill_failure_releases_the_gate():
    budget = MemoryBudget(1024)
    with patch.object(budget, '_spill', side_effect=RuntimeError('spill failed')):
        with pytest.raises(RuntimeError, match='spill failed'):
            budget.fetch('x', 'key', lambda: np.ones(4), spill=Path('unused'))
    assert budget._computing == {}


def test_waiter_hit_releases_its_registration():
    _check_waiters('cached')


def test_waiters_stay_serialized_after_failure():
    _check_waiters('failure')


def test_waiters_stay_serialized_for_oversized_results():
    _check_waiters('oversized')


def test_waiters_stay_serialized_after_eviction():
    _check_waiters('evicted')


def _check_waiters(mode):
    budget = MemoryBudget(16 if mode == 'oversized' else 1024)
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    release_second = threading.Event()
    state_lock = threading.Lock()
    active = 0
    maximum_active = 0
    calls = 0
    value = np.ones(16, dtype=np.float32)

    def compute():
        nonlocal active, maximum_active, calls
        with state_lock:
            calls += 1
            index = calls
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            if index == 1:
                first_started.set()
                assert release_first.wait(5), 'first caller timed out'
                if mode == 'failure':
                    raise ValueError('first failed')
            elif index == 2:
                second_started.set()
                assert release_second.wait(5), 'second caller timed out'
            return value
        finally:
            with state_lock:
                active -= 1

    def fetch():
        return budget.fetch('x', 'key', compute)

    def wait_for_users(count):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with budget._lock:
                gate = budget._computing.get(('x', 'key'))
                if gate is not None and gate.users == count:
                    return gate
            time.sleep(0.001)
        raise AssertionError(f'expected {count} registered callers')
    original_put = budget.put

    def put_and_evict(*args, **kwargs):
        original_put(*args, **kwargs)
        budget.discard('x', 'key')
    patcher = patch.object(budget, 'put', side_effect=put_and_evict)
    if mode == 'evicted':
        patcher.start()
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            try:
                first = pool.submit(fetch)
                assert first_started.wait(5)
                second = pool.submit(fetch)
                gate = wait_for_users(2)
                release_first.set()
                if mode == 'failure':
                    with pytest.raises(ValueError, match='first failed'):
                        first.result(timeout=5)
                else:
                    assert first.result(timeout=5) is value
                if mode != 'cached':
                    assert second_started.wait(5)
                    third = pool.submit(fetch)
                    assert wait_for_users(2) is gate
                    release_second.set()
                    assert third.result(timeout=5) is value
                assert second.result(timeout=5) is value
            finally:
                release_first.set()
                release_second.set()
    finally:
        if mode == 'evicted':
            patcher.stop()
    assert maximum_active == 1
    expected_calls = 1 if mode == 'cached' else 3 if mode in {'oversized', 'evicted'} else 2
    assert calls == expected_calls
    assert budget._computing == {}
