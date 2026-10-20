"""Installed audio plug-ins, and a fuzzy match from a typed name to one of them.

The automixer takes plug-in PATHS (``--speech-plugins``). The owner should not have to
type one, so the dialog lists what is installed and matches loosely: ``dxrev`` finds
"Accentize dxRevive".

The scan only lists directory entries. It never opens, loads or executes a plug-in
(a plug-in is code; ``Contents/`` is not read), and an entry that is a symlink pointing
outside the plug-in folder is skipped. The matcher has a twin in ``ui/plugin-match.js``
(same rules, same table in the tests); keep them in step.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

#: The folder names under macOS's Plug-Ins/ (the format is read from the extension).
_MAC = ("VST3", "Components", "VST")
#: How deep below a plug-in folder an entry may sit (vendor sub-folders exist).
MAX_DEPTH = 2
#: Preferred format when one name is installed in several: VST3, then AU, then VST2.
FORMAT_RANK = {"VST3": 0, "AU": 1, "VST2": 2}
DEFAULT_LIMIT = 8
#: A typo (one edit) is only tolerated for a name this long and a query this long;
#: shorter ones would match nearly everything.
TYPO_MIN_NAME = 5
TYPO_MIN_QUERY = 4

_lock = threading.Lock()
_cache: list[dict] | None = None


def roots(platform: str | None = None, home: Path | None = None) -> list[Path]:
    """The standard plug-in folders of this platform (those that may not exist too)."""
    platform = platform or sys.platform
    home = home or Path.home()
    if platform == "darwin":
        base = [Path("/Library/Audio/Plug-Ins"), home / "Library/Audio/Plug-Ins"]
        return [b / folder for b in base for folder in _MAC]
    if platform.startswith("win"):
        common = Path(os.environ.get("COMMONPROGRAMFILES",
                                     r"C:\Program Files\Common Files"))
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        return [common / "VST3", local / "Programs/Common/VST3"]
    if platform.startswith("linux"):
        return [home / ".vst3", Path("/usr/lib/vst3"), Path("/usr/local/lib/vst3"),
                home / ".vst", Path("/usr/lib/vst"), Path("/usr/local/lib/vst")]
    return []


def _format_of(root: Path, name: str) -> tuple[str, str] | None:
    """``(format, extension)`` an entry named ``name`` under ``root`` has, or None."""
    lower = name.lower()
    for fmt, ext in (("VST3", ".vst3"), ("AU", ".component"), ("VST2", ".vst"),
                     ("VST2", ".so")):
        if lower.endswith(ext) and len(name) > len(ext):
            # .so is a VST2 only in a "vst" folder; .vst3 under a "vst" folder is a VST3.
            if ext == ".so" and root.name.lower() not in ("vst", "lxvst"):
                continue
            return fmt, ext
    return None


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def scan(folders: list[Path] | None = None) -> list[dict]:
    """Every plug-in found in ``folders`` (default: this platform's), as
    ``{"name", "format", "path"}`` (name without extension, absolute path), sorted by
    name. Only names are read."""
    found: list[dict] = []
    for root in roots() if folders is None else folders:
        found.extend(_scan_one(Path(root)))
    found.sort(key=lambda p: (p["name"].lower(), FORMAT_RANK.get(p["format"], 9),
                              p["path"]))
    return found


def _scan_one(root: Path) -> list[dict]:
    out: list[dict] = []
    if not root.is_dir():
        return out
    stack = [(root, 0)]
    while stack:
        folder, depth = stack.pop()
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink() and not _inside(path, root):
                continue
            kind = _format_of(root, entry.name)
            if kind is not None:
                if entry.is_dir() or kind[1] == ".so":
                    out.append({"name": entry.name[:-len(kind[1])], "format": kind[0],
                                "path": str(path.absolute())})
                continue
            if depth + 1 < MAX_DEPTH and entry.is_dir(follow_symlinks=False):
                stack.append((path, depth + 1))
    return out


def list_plugins(refresh: bool = False) -> list[dict]:
    """The installed plug-ins, scanned once per session and again when ``refresh``."""
    global _cache  # noqa: PLW0603 - the session cache
    with _lock:
        if _cache is None or refresh:
            _cache = scan()
        return list(_cache)


# -- fuzzy matching ---------------------------------------------------------------------


def _chars(text: str) -> tuple[str, list[int], list[int]]:
    """``(compact, origin, word_starts)``: the letters and digits of ``text`` lowercased
    and joined, the index in ``text`` of each, and the compact index each word starts
    at."""
    compact: list[str] = []
    origin: list[int] = []
    starts: list[int] = []
    inside = False
    for i, ch in enumerate(text):
        if ch.isalnum():
            if not inside:
                starts.append(len(compact))
            inside = True
            compact.append(ch.lower())
            origin.append(i)
        else:
            inside = False
    return "".join(compact), origin, starts


def edit_distance(a: str, b: str) -> int:
    """Damerau-Levenshtein (optimal string alignment): insert, delete, replace, swap."""
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        row = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            row[j] = min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                row[j] = min(row[j], prev2[j - 2] + 1)
        prev2, prev = prev, row
    return prev[len(b)]


def _tier(q: str, compact: str, starts: list[int]) -> tuple[str, list[int]] | None:
    """``(tier, compact indices matched)`` of query ``q`` against a name, or None."""
    n = len(q)
    if compact == q:
        return "exact", list(range(n))
    if compact.startswith(q):
        return "prefix", list(range(n))
    for s in starts:
        if compact.startswith(q, s):
            return "word", list(range(s, s + n))
    at = 0
    picked: list[int] = []
    for ch in q:
        at = compact.find(ch, at)
        if at < 0:
            break
        picked.append(at)
        at += 1
    else:
        return "subsequence", picked
    if len(compact) >= TYPO_MIN_NAME and n >= TYPO_MIN_QUERY:
        for s in [0, *starts]:
            for size in (n - 1, n, n + 1):
                if edit_distance(q, compact[s:s + size]) <= 1:
                    return "typo", []
    return None


TIERS = ("exact", "prefix", "word", "subsequence", "typo")


def match(query: str, items: list[dict], limit: int = DEFAULT_LIMIT) -> list[dict]:
    """The best ``limit`` of ``items`` for ``query``: case, spaces and punctuation are
    ignored; exact beats prefix beats word-prefix beats subsequence beats a one-edit typo;
    one entry per name (VST3 over AU over VST2). Each answer is the item plus ``tier``
    and ``indices`` (positions in the name to highlight)."""
    q, _o, _s = _chars(query)
    if not q:
        return []
    best: dict[str, dict] = {}
    for item in items:
        key = _chars(item["name"])[0]
        old = best.get(key)
        if old is None or (FORMAT_RANK.get(item["format"], 9)
                           < FORMAT_RANK.get(old["format"], 9)):
            best[key] = item
    rows = []
    for key, item in best.items():
        compact, origin, starts = _chars(item["name"])
        hit = _tier(q, compact, starts)
        if hit is None:
            continue
        tier, picked = hit
        rows.append((TIERS.index(tier), len(key), item["name"].lower(),
                     {**item, "tier": tier, "indices": [origin[i] for i in picked]}))
    rows.sort(key=lambda r: r[:3])
    return [r[3] for r in rows[:limit]]


def looks_like_path(text: str) -> bool:
    """Free text that names a file rather than a plug-in: it has a path separator."""
    return "/" in text or "\\" in text or text.startswith("~")


def resolve(text: str, items: list[dict]) -> str | None:
    """The path a typed plug-in name stands for: the best match, or None."""
    top = match(text, items, limit=1)
    return top[0]["path"] if top else None
