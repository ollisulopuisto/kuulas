"""The page as served: ``index.html`` with its module graph preloaded.

The UI is plain ES modules with no build step (``ui/``, 216 files, 1.5 MB).
Left to the browser, ``app.js`` and its 118 imports are discovered one level
at a time: four fetch levels, and with HTTP/1.1's six connections per host
the modules alone took 1.0 s (median of 7 cold loads, headless Chrome,
2026-10-21). Served at ~1.3 ms per request the same 196 files take 0.3 s
when the browser knows them all up front, so the page gets one
``<link rel="modulepreload">`` per module, in breadth-first order from
``app.js`` (what is needed first is asked for first).

The graph is computed once at app creation by reading the import statements
(no bundler, no manifest to keep in sync); a module added while the server
runs is simply fetched the old way until the next start.
"""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path

#: Static ``import``/``export ... from`` statements naming a sibling module. Only
#: the relative, same-folder form the UI uses (``"./name.js"``); ``import()`` calls
#: are left alone (they are deferred on purpose).
_STATIC_IMPORT = re.compile(
    r"""^\s*(?:import|export)\b[^;]*?\bfrom\s+["']\./([^"']+)["']\s*;?"""
    r"""|^\s*import\s+["']\./([^"']+)["']\s*;?""",
    re.MULTILINE,
)

#: The entry script tag; group 1 is its indentation, kept for the links.
_ENTRY_TAG = re.compile(r"""([ \t]*)<script\s+type="module"\s+src="/([^"]+)"></script>""")


def static_imports(text: str) -> list[str]:
    """The sibling modules ``text`` imports statically, in source order."""
    found = []
    for match in _STATIC_IMPORT.finditer(text):
        name = match.group(1) or match.group(2)
        if name not in found:
            found.append(name)
    return found


def module_graph(ui: Path, entry: str) -> list[str]:
    """Every module reachable from ``entry`` by static imports, breadth first,
    without ``entry`` itself; names that are not files are dropped."""
    seen = {entry}
    order: list[str] = []
    queue = deque([entry])
    while queue:
        current = queue.popleft()
        path = ui / current
        if not path.is_file():
            continue
        for name in static_imports(path.read_text(encoding="utf-8")):
            if name in seen or not (ui / name).is_file():
                continue
            seen.add(name)
            order.append(name)
            queue.append(name)
    return order


def index_html(ui: Path) -> str:
    """``index.html`` with a ``modulepreload`` link for each module its entry
    script reaches, placed just before that script tag (same indentation)."""
    page = (ui / "index.html").read_text(encoding="utf-8")
    match = _ENTRY_TAG.search(page)
    if match is None:
        return page
    indent, entry = match.group(1), match.group(2)
    links = "".join(f'{indent}<link rel="modulepreload" href="/{name}" />\n'
                    for name in module_graph(ui, entry))
    return page[:match.start()] + links + page[match.start():]
