"""Take and channel names, and the file names made from them.

Shared by the supervisor and the worker; no audio, no numpy.
"""

from __future__ import annotations

import re

# Letters (any script), digits, space and a few marks. No path separators, no
# "~" (it numbers the files of later segments), no leading dot or space.
_NAME = re.compile(r"[^\W_][\w .,()'+&-]{0,79}", re.UNICODE)


def valid_name(name: object) -> bool:
    return (isinstance(name, str) and _NAME.fullmatch(name) is not None
            and not name.endswith((" ", ".")))


def segment_file(take: str, name: str, segment: int) -> str:
    """``<take>-<name>.wav`` for the first segment, ``<take>-<name>~<n>.wav`` after.

    A take has a new segment after each worker restart, device return or
    4 GB file limit; ``<take>.take.json`` lists them with their start frames.
    """
    if segment == 1:
        return f"{take}-{name}.wav"
    return f"{take}-{name}~{segment}.wav"


def sidecar_file(take: str) -> str:
    return f"{take}.take.json"


def journal_file(take: str) -> str:
    return f"{take}.journal.jsonl"
