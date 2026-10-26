"""Remove the filler words (um, uh, öö ...) from a kuulas project.

No LLM, no server, no window.

    uv run python scripts/examples/remove_fillers.py Episode.kuulas
    uv run python scripts/examples/remove_fillers.py Episode.kuulas --dry-run

This is the worked example of docs/SCRIPTING.md: open the project folder with ``Session``,
read the words someone hears, and run the same command the transcript's X key runs
(``cut_words``). Every cut is one undo step, so open the project afterwards and undo what
you do not like. The project must not be open in a window (a second session on it is
read-only).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from kuulas.session import Session

# What counts as a filler: the word in lower case, no punctuation round it. Add your own.
FILLERS = frozenset(
    {"um", "umm", "uh", "uhh", "er", "erm", "hmm", "mm", "öö", "ööö", "ee", "eee"})

_EDGES = re.compile(r"^\W+|\W+$")


def is_filler(text: str, fillers: frozenset[str] = FILLERS) -> bool:
    """"Um," and "UM" are fillers too: case and punctuation at the ends do not matter."""
    return _EDGES.sub("", text).casefold() in fillers


def find_fillers(words: list[dict], fillers: frozenset[str] = FILLERS) -> list[int]:
    """The positions in ``words`` (``Session.heard_words()``) of the filler words."""
    return [i for i, word in enumerate(words) if is_filler(word["w"], fillers)]


def remove_fillers(session: Session, fillers: frozenset[str] = FILLERS) -> dict:
    """Cut every run of filler words out of the audio, one undo step per run.

    ``cut_words`` removes the whole stretch from its first to its last word, so words that
    are not next to each other cannot go in one call: the words in between would go too. A
    run of fillers side by side ("um uh") is one cut. The last run goes first and the
    words are read again each time, so the positions are those of the words as they are.
    Returns {"words": how many were removed, "cuts": how many cuts it took}.
    """
    removed = cuts = 0
    while True:
        found = find_fillers(session.heard_words(), fillers)
        if not found:
            return {"words": removed, "cuts": cuts}
        run = [found[-1]]
        while run[0] - 1 in found:
            run.insert(0, run[0] - 1)
        session.command("cut_words", {"indices": run})
        removed += len(run)
        cuts += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("folder", type=Path, help="the Name.kuulas project folder")
    parser.add_argument("--dry-run", action="store_true",
                        help="only list the fillers found")
    args = parser.parse_args(argv)
    session = Session(args.folder)
    try:
        if args.dry_run:
            words = session.heard_words()
            found = find_fillers(words)
            print(f"{len(found)} filler words:", ", ".join(words[i]["w"] for i in found))
            return 0
        if session.read_only:
            print("The project is open in another window: close it first.",
                  file=sys.stderr)
            return 1
        done = remove_fillers(session)
        print(f"Removed {done['words']} filler words in {done['cuts']} cuts.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
