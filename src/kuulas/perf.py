"""Named counters for the performance report (Help > Record a performance report).

Each counter keeps how often it was noted, the sum and the largest value. ``note`` is a
dict lookup and three assignments, with no lock and no allocation once the name exists,
so the audio thread can call it. Two threads noting the same name at once can lose an
update; for a report that shows averages over thousands of blocks that does not matter.

The report asks for a ``snapshot`` when a recording starts and again when it ends and
shows the ``delta``, so it describes the span and not the whole run.
"""

from __future__ import annotations


class Counters:
    def __init__(self) -> None:
        #: name -> [count, total, max]
        self._c: dict[str, list[float]] = {}

    def note(self, name: str, value: float) -> None:
        c = self._c.get(name)
        if c is None:
            c = self._c.setdefault(name, [0, 0.0, 0.0])
        c[0] += 1
        c[1] += value
        c[2] = max(c[2], value)

    def snapshot(self) -> dict[str, dict[str, float]]:
        return {name: {"count": int(c[0]), "total": c[1], "max": c[2]}
                for name, c in list(self._c.items())}

    def reset_max(self) -> None:
        """Forget the peaks (the report wants the worst value *in its span*)."""
        for c in list(self._c.values()):
            c[2] = 0.0


def delta(before: dict[str, dict[str, float]],
          after: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """What was noted between two snapshots; names that did not move are left out.
    ``max`` is the later snapshot's (see ``Counters.reset_max``)."""
    out = {}
    for name, now in after.items():
        was = before.get(name, {"count": 0, "total": 0.0})
        count = now["count"] - was["count"]
        if count > 0:
            out[name] = {"count": count, "total": now["total"] - was["total"],
                         "max": now["max"]}
    return out


#: The process-wide counters.
COUNTERS = Counters()
