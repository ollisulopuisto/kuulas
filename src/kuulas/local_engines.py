"""Which local transcription engine runs when nobody said: the one place that decides.

Two questions, two answers (both are names of the engines the UI offers):

* ``DEFAULT``: a new request that names no engine (the HTTP route, ``Session.transcribe``,
  the agent tools). The page names one too; when it does not, the server decides.
* ``LEGACY``: a job file that has no ``local_engine``. Such files were written before the
  engine selector existed, when the only local engine was Orukeet, so the worker still
  runs them as Orukeet. It is not the default for new requests and must not follow it.
"""

from __future__ import annotations

ENGINES = ("whisper", "orukeet")
DEFAULT = "whisper"
LEGACY = "orukeet"


def of_job(job: dict) -> str:
    """The engine a job file asks for: its own ``local_engine``, else ``LEGACY``."""
    return job.get("local_engine") or LEGACY
