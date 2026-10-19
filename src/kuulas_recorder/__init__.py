"""kuulas-recorder: the standalone recording program (WP12a part A, docs/RECORDER.md).

It imports nothing from the editor (``kuulas``): the editor is only a client on
a local socket, so quitting or crashing the editor never stops a recording.
The owner's rule decides every choice here: audio already recorded is never
lost.
"""

from importlib import metadata

# The control protocol's version (docs/RECORDER.md). Bump it when a command or
# event changes in a way an older client would misread. 2: pre-roll and several
# channels are in (``arm``, ``channel_failed``); an editor that needs them replaces
# an idle recorder that reports 1 (never one that is recording).
PROTOCOL = 2

# The take sidecar's format version (``<take>.take.json``).
TAKE_FORMAT = 1


def version() -> str:
    """The installed kuulas distribution's version (the recorder ships in it)."""
    try:
        return metadata.version("kuulas")
    except metadata.PackageNotFoundError:
        return "unknown"
