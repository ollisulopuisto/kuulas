"""Protected files: never delete recordings or linked media by mistake.

``is_protected`` decides whether ``path`` is a recording under
``<project_root>/recordings/`` (any depth) or one of the linked ``media_paths``.
``check_delete`` returns ``"ok"`` when a deletion may proceed and ``"refused"``
for a protected file unless it was confirmed.

``..`` segments are resolved textually with ``os.path.normpath``; nothing ever
touches the disk. Matching is case-sensitive. Relative paths raise
``ValueError``; there is no user-facing text.
"""

from __future__ import annotations

import os.path
from pathlib import PurePath


def _require_absolute(path: str, name: str) -> str:
    if not PurePath(path).is_absolute():
        msg = f"{name} must be an absolute path, got {path!r}"
        raise ValueError(msg)
    return path


def is_protected(path: str, project_root: str, media_paths: tuple[str, ...] = ()) -> bool:
    """Return True when ``path`` is a recording or linked media file."""
    _require_absolute(project_root, "project_root")
    _require_absolute(path, "path")
    for media in media_paths:
        _require_absolute(media, "media_paths entry")
    root = os.path.normpath(project_root)
    p = os.path.normpath(path)
    recordings = os.path.normpath(os.path.join(root, "recordings"))
    if p == recordings or p.startswith(recordings + os.path.sep):
        return True
    return any(p == os.path.normpath(media) for media in media_paths)


def check_delete(
    path: str,
    project_root: str,
    media_paths: tuple[str, ...] = (),
    confirmed: bool = False,
) -> str:
    """Return ``"ok"`` when the deletion may proceed, else ``"refused"``."""
    if is_protected(path, project_root, media_paths):
        return "ok" if confirmed else "refused"
    return "ok"
