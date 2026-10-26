import pytest

from kuulas_recorder.sources import SourceError, resolve_device


def test_resolve_device_by_name_and_index_exact_match():
    devices = [{"index": 0, "name": "A"}, {"index": 1, "name": "B"}]
    assert resolve_device(devices, {"index": 1, "name": "B"}) == {"index": 1, "name": "B"}


def test_resolve_device_by_name_and_index_name_wins():
    devices = [{"index": 0, "name": "A"}, {"index": 2, "name": "B"}]
    # Device B changed index from 1 to 2, name match should still find it.
    assert resolve_device(devices, {"index": 1, "name": "B"}) == {"index": 2, "name": "B"}


def test_resolve_device_by_name_only():
    devices = [{"index": 0, "name": "A"}, {"index": 1, "name": "B"}]
    assert resolve_device(devices, "B") == {"index": 1, "name": "B"}
    assert resolve_device(devices, {"name": "B"}) == {"index": 1, "name": "B"}


def test_resolve_device_by_index_only():
    devices = [{"index": 0, "name": "A"}, {"index": 1, "name": "B"}]
    assert resolve_device(devices, 1) == {"index": 1, "name": "B"}
    assert resolve_device(devices, {"index": 1}) == {"index": 1, "name": "B"}


def test_resolve_device_default():
    devices = [{"index": 0, "name": "A"}, {"index": 1, "name": "B", "default": True}]
    assert resolve_device(devices, None) == {"index": 1, "name": "B", "default": True}
    assert resolve_device(devices, True) == {"index": 1, "name": "B", "default": True}
    assert resolve_device(devices, False) == {"index": 1, "name": "B", "default": True}
    assert resolve_device(devices, {}) == {"index": 1, "name": "B", "default": True}


def test_resolve_device_not_found_errors():
    devices = [{"index": 0, "name": "A"}]

    with pytest.raises(SourceError) as exc_info:
        resolve_device(devices, "B")
    assert exc_info.value.key == "device_not_found"
    assert "B" in exc_info.value.text

    with pytest.raises(SourceError) as exc_info:
        resolve_device(devices, {"name": "B", "index": 0})
    assert exc_info.value.key == "device_not_found"

    with pytest.raises(SourceError) as exc_info:
        resolve_device(devices, 1)
    assert exc_info.value.key == "device_not_found"
    assert "1" in exc_info.value.text

    with pytest.raises(SourceError) as exc_info:
        resolve_device(devices, None)
    assert exc_info.value.key == "device_not_found"
    assert "default" in exc_info.value.text
