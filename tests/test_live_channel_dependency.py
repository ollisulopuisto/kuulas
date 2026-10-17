"""`kuulas open` serves /api/live: that needs a WebSocket library installed."""

import importlib.util


def test_a_websocket_library_is_installed():
    assert importlib.util.find_spec("websockets") is not None
