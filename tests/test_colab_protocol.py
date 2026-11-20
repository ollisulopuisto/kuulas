"""Kuulas ajaa colab-transcriben uvx:llä podcast-varastosta pinnatusta
commitista. Istunnon-kadonneet-tunnistus ja pinni eivät saa ajautua
eroon podcast-puolen lähteestä (omistaja 20.11: "Make it so podcast
and Kuulas cannot diverge here")."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from kuulas import colab_transcribe

KUULAS_ROOT = Path(__file__).resolve().parents[1]
PODCAST_ROOT = KUULAS_ROOT.parent / "podcast"
SESSION_PY = (
    PODCAST_ROOT / "colab-transcribe" / "src" / "colabtranscribe" / "session.py"
)

pytestmark = pytest.mark.skipif(
    not (PODCAST_ROOT / ".git").exists(),
    reason="podcast-sisarvarasto puuttuu (CI checkaa sen aina viereen)",
)

#: Rivimuotoja, joita Colab CLI on todettu tulostavan kadonneesta istunnosta
#: (0.7.5 "not found", käyttäjäraportti 19.11; vanhempi "appears to be lost").
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
    assert m, "podcast session.py: SESSION_GONE-lähde puuttuu tai muuttua muotoa"
    return m.group(1)


def test_session_gone_pattern_matches_podcast():
    assert colab_transcribe._SESSION_LOST.pattern == _podcast_pattern(), (
        "kuulas _SESSION_LOST ja podcast SESSION_GONE ovat eronneet: "
        "synkkaa säännöllinen lauseke podcast-puolelta"
    )


def test_session_gone_corpus_agrees_on_both_sides():
    podcast_re = re.compile(_podcast_pattern())
    for line in CORPUS_HIT:
        assert colab_transcribe._SESSION_LOST.search(line), line
        assert podcast_re.search(line), line
    for line in CORPUS_MISS:
        assert not colab_transcribe._SESSION_LOST.search(line), line
        assert not podcast_re.search(line), line


def _podcast_subtree_head() -> str:
    git = shutil.which("git")
    assert git, "git puuttuu polusta"
    # Kiinteät argumentit: ei käyttäjän syötettä.
    return subprocess.run(  # noqa: S603
        [git, "-C", str(PODCAST_ROOT), "log", "-1", "--format=%H", "origin/main", "--",
         "colab-transcribe/"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_remote_source_pin_is_the_podcast_subtree_head():
    m = re.search(r"podcast@([0-9a-f]{40})", colab_transcribe._REMOTE_SOURCE)
    assert m, "_REMOTE_SOURCE ei sisällä tunnistettavaa commit-tiivistettä"
    head = _podcast_subtree_head()
    assert m.group(1) == head, (
        f"_REMOTE_SOURCE on pinnattu {m.group(1)[:8]}:aan mutta podcast mainin "
        f"colab-transcribe-alipuu on {head[:8]}: nosta pinni"
    )
