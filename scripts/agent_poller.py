#!/usr/bin/env python3
"""Nudge the opencode session when the coordinator has written new instructions.

Run every 5 minutes by launchd. A tick makes no model call unless
`.agents/opencode.md` changed since the last nudge and the session is idle.
Talks to the opencode server on 127.0.0.1:4096; if it is down, does nothing.
The server password is read from its launchd plist, never printed or logged.

    agent_poller.py            check once, nudge if needed
    agent_poller.py --dry-run  say what would happen, change nothing
"""

from __future__ import annotations

import base64
import hashlib
import json
import plistlib
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AGENT_FILE = REPO / ".agents" / "opencode.md"
STATE = REPO / ".agents" / ".poller-state.json"
LOG = REPO / ".agents" / "poller.log"
PLIST = Path.home() / "Library/LaunchAgents/ai.opencode.server.plist"
BASE = "http://127.0.0.1:4096"
PROMPT = (
    f"Coordinator: {AGENT_FILE} has new instructions. Re-read it, then continue "
    "with your next open task under the rules there. Report in opencode-reply.md.")


def should_nudge(current: str, last: str | None, messages: list[dict]) -> bool:
    """True when the instructions changed and the session is idle."""
    if current == last:
        return False
    if not messages:
        return True
    newest = messages[-1]["info"]
    if newest["role"] == "user":
        return False
    return newest.get("time", {}).get("completed") is not None


def pick_session(sessions: list[dict], directory: str) -> str | None:
    """The most recently updated session that works in ``directory``."""
    mine = [s for s in sessions if s.get("directory") == directory]
    if not mine:
        return None
    return max(mine, key=lambda s: s.get("time", {}).get("updated", 0))["id"]


def _auth() -> str:
    password = plistlib.loads(PLIST.read_bytes())["EnvironmentVariables"][
        "OPENCODE_SERVER_PASSWORD"]
    return "Basic " + base64.b64encode(f"opencode:{password}".encode()).decode()


def _call(path: str, body: dict | None = None):
    request = urllib.request.Request(  # noqa: S310 (fixed http://127.0.0.1 URL)
        BASE + path, headers={"Authorization": _auth(),
                              "Content-Type": "application/json"},
        data=None if body is None else json.dumps(body).encode(),
        method="GET" if body is None else "POST")
    with urllib.request.urlopen(request, timeout=20) as reply:  # noqa: S310
        data = reply.read()
    return json.loads(data) if data else None


def _log(text: str) -> None:
    stamp = time.strftime("%d.%m.%Y %H.%M %Z")
    with LOG.open("a") as out:
        out.write(f"{stamp}: {text}\n")


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    current = hashlib.sha256(AGENT_FILE.read_bytes()).hexdigest()
    last = json.loads(STATE.read_text()).get("hash") if STATE.exists() else None
    if current == last:
        return 0
    try:
        session = pick_session(_call("/session"), str(REPO))
        if session is None:
            _log("no opencode session for this repo; nothing to nudge")
            return 0
        messages = _call(f"/session/{session}/message")
    except OSError as error:
        _log(f"server not reachable: {error}")
        return 0
    if not should_nudge(current, last, messages):
        _log(f"{session}: busy, will retry")
        return 0
    if dry:
        print(f"would nudge {session}")
        return 0
    _call(f"/session/{session}/prompt_async",
          {"parts": [{"type": "text", "text": PROMPT}]})
    STATE.write_text(json.dumps({"hash": current, "session": session}))
    _log(f"{session}: nudged")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
