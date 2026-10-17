"""The 5-minute agent poller: when it nudges, and when it stays quiet."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "agent_poller", Path(__file__).parent.parent / "scripts" / "agent_poller.py")
poller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poller)


def msg(role, completed):
    return {"info": {"role": role, "time": {"completed": completed}}}


def test_idle_session_with_changed_instructions_is_nudged():
    assert poller.should_nudge("new", "old", [msg("assistant", 5)]) is True


def test_unchanged_instructions_are_not_nudged_twice():
    assert poller.should_nudge("same", "same", [msg("assistant", 5)]) is False


def test_busy_session_is_left_alone():
    assert poller.should_nudge("new", "old", [msg("assistant", None)]) is False


def test_a_prompt_the_agent_has_not_answered_yet_counts_as_busy():
    assert poller.should_nudge("new", "old", [msg("user", None)]) is False


def test_empty_session_is_idle():
    assert poller.should_nudge("new", "old", []) is True


def test_newest_session_in_the_repo_is_chosen():
    sessions = [
        {"id": "a", "directory": "/other", "time": {"updated": 9}},
        {"id": "b", "directory": "/repo", "time": {"updated": 1}},
        {"id": "c", "directory": "/repo", "time": {"updated": 3}},
    ]
    assert poller.pick_session(sessions, "/repo") == "c"
    assert poller.pick_session(sessions, "/none") is None
