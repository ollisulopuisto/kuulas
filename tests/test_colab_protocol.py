"""Kuulas runs colab-transcribe through uvx, pinned to a podcast repo
commit. The session-gone detector and the pin must not drift away from
the podcast side (owner 20.11: "Make it so podcast and Kuulas cannot
diverge here")."""

import re
import shutil
import subprocess
from pathlib import Path

from kuulas import colab_transcribe

KUULAS_ROOT = Path(__file__).resolve().parents[1]
PODCAST_ROOT = KUULAS_ROOT.parent / "podcast"
SESSION_PY = (
    PODCAST_ROOT / "colab-transcribe" / "src" / "colabtranscribe" / "session.py"
)


def _require_podcast() -> None:
    """The sibling clone is mandatory: silently skipping would make the
    checks vacuous (repo rule: no skipped tests, Devin #269)."""
    assert (PODCAST_ROOT / ".git").exists(), (
        f"podcast sibling clone missing: clone ollisulopuisto/podcast "
        f"into {PODCAST_ROOT.parent} (CI always checks it out there)"
    )


#: Wordings the Colab CLI is known to print for a dead session
#: (0.7.5 "not found", user report 19.11; older "appears to be lost").
CORPUS_HIT = [
    "Session 'whisper' not found.",
    "Session 'myrun' appears to be lost",
    "prefix Session 'x' not found. suffix",
]
CORPUS_MISS = [
    "Session 'whisper' created.",
    "File or directory not found: /content/cache/abc/data.wav.flac.part0076",
    "Session started",
    "",
]


def _podcast_pattern() -> str:
    source = SESSION_PY.read_text(encoding="utf-8")
    m = re.search(r"SESSION_GONE = re\.compile\(r\"(.*?)\"\)", source)
    assert m, "podcast session.py: SESSION_GONE source missing or shape changed"
    return m.group(1)


def test_session_gone_pattern_matches_podcast():
    _require_podcast()
    assert colab_transcribe._SESSION_LOST.pattern == _podcast_pattern(), (
        "kuulas _SESSION_LOST and podcast SESSION_GONE have drifted: "
        "sync the regex from the podcast side"
    )


def test_session_gone_corpus_agrees_on_both_sides():
    _require_podcast()
    podcast_re = re.compile(_podcast_pattern())
    for line in CORPUS_HIT:
        assert colab_transcribe._SESSION_LOST.search(line), line
        assert podcast_re.search(line), line
    for line in CORPUS_MISS:
        assert not colab_transcribe._SESSION_LOST.search(line), line
        assert not podcast_re.search(line), line


def _git(*args: str) -> str:
    git = shutil.which("git")
    assert git, "git not on PATH"
    # Fixed literal arguments only: no user input.
    return subprocess.run(  # noqa: S603
        [git, "-C", str(PODCAST_ROOT), *args],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _subtree_tree(rev: str) -> str:
    """The tree object id of colab-transcribe/ at rev: content equality
    without history walking, so a depth-one CI checkout is enough
    (Devin #269)."""
    return _git("rev-parse", f"{rev}:colab-transcribe")


def test_remote_source_pin_matches_the_podcast_subtree():
    _require_podcast()
    m = re.search(r"podcast@([0-9a-f]{40})", colab_transcribe._REMOTE_SOURCE)
    assert m, "_REMOTE_SOURCE carries no recognizable commit hash"
    pin = m.group(1)
    try:
        _git("cat-file", "-e", f"{pin}^{{commit}}")
    except subprocess.CalledProcessError:
        # Shallow checkout: fetch just the pinned commit (GitHub allows
        # fetching reachable commits by hash).
        _git("fetch", "--depth=1", "origin", pin)
        _git("cat-file", "-e", "FETCH_HEAD^{commit}")
        pin_ref = "FETCH_HEAD"
    else:
        pin_ref = pin
    assert _subtree_tree(pin_ref) == _subtree_tree("origin/main"), (
        f"the pinned colab-transcribe tree at {pin[:8]} differs from "
        f"podcast main's: bump _REMOTE_SOURCE to a current main commit"
    )
