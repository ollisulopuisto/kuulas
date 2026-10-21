#!/usr/bin/env python3
"""Drop requirements the bundled automixer does not use, in a COPY of its pyproject.

    trim_deps.py <pyproject.toml>      (rewrites that file; build_wheels.sh passes a copy)

The automixer requires mlx and textual unconditionally, but only its TUI and its
in-memory route import them; Kuulas runs the folder route (``automixer <stems-folder>``),
whose imports and ``--help`` load neither (checked on podcast main 8127aa7). mlx also
publishes no wheel for the bundle's macOS 12 target, so the .dmg build failed on it
(2026-10-21), and it would add about 45 MB to the .dmg. The clean fix is extras in the
podcast repo (docs/PODCAST-MAGIC.md, "Automixer in the dmg"); once they are, this is a
no-op and says so. ``[tool.uv.sources]`` goes too: the copy is outside the podcast
workspace its ``workspace = true`` entries point at.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

#: Requirement names the folder route never imports.
UNUSED = ("mlx", "textual")


def _name(line: str) -> str | None:
    found = re.match(r'\s*["\']([A-Za-z0-9_.-]+)', line)
    return found.group(1).lower().replace("_", "-") if found else None


def trim(text: str, names: tuple[str, ...]) -> str:
    """``text`` (a pyproject) without the ``[project] dependencies`` lines naming one of
    ``names`` and without the ``[tool.uv.sources]`` table. One requirement per line, as
    the automixer's file has them."""
    out: list[str] = []
    in_deps = in_sources = False
    removed: set[str] = set()
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if re.match(r"\[[A-Za-z]", line):  # a table header, at the start of a line
            in_sources = stripped == "[tool.uv.sources]"
        if in_sources:
            continue
        if re.match(r"dependencies\s*=\s*\[", stripped):
            in_deps = True
        elif in_deps and stripped.startswith("]"):
            in_deps = False
        elif in_deps and _name(line) in names:
            removed.add(_name(line) or "")
            continue
        out.append(line)
    result = "".join(out)
    tomllib.loads(result)  # still a valid file
    for name in names:
        if name not in removed:
            print(f"trim_deps: {name} is not a requirement any more; "
                  "this trim can go", file=sys.stderr)
    return result


def main() -> None:
    path = Path(sys.argv[1])
    path.write_text(trim(path.read_text(encoding="utf-8"), UNUSED), encoding="utf-8")


if __name__ == "__main__":
    main()
