"""The options of Auto-Silence, and their checking (pure, no I/O).

The defaults are the values that used to be hard-coded in ``analysis``, so a
run without options gives exactly the old result. Numbers are clamped to
their range (a slider cannot say anything absurd, a hand-edited call is
tamed); something that is not a number at all is refused.

* ``margin_db``: how far above the track's own noise floor a hop counts as
  talk. Lower = gentler: fewer stretches closed.
* ``dominance_db``: how close to the loudest mic another mic may be and still
  count as open (speechmix ``duck_dominance_db``). Higher = stricter about
  bleed from other mics: a mic must be this far from the loudest to stay open.
* ``min_open_s`` / ``min_closed_s``: the merge of WP44 (see ``analysis``).
* ``open_before_s`` / ``open_after_s``: speech onset and tail kept open.
* ``method``: ``threshold`` (floor + margin, then the bleed ducking) or
  ``compensated`` (each mic against the others, corrected for how much each
  normally hears of them: ``bleed_relative``; needs the owner's hand mutes).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from speechmix import grid, masks

from .ops import EditError

METHODS = ("threshold", "compensated")

#: The merge defaults of WP44 (tuning notes: ``analysis``).
DEFAULT_MIN_OPEN_S = 0.4
DEFAULT_MIN_CLOSED_S = 0.3

#: option -> (lowest, highest).
RANGES: dict[str, tuple[float, float]] = {
    "margin_db": (3.0, 20.0),
    "dominance_db": (0.0, 30.0),
    "min_open_s": (0.0, 5.0),
    "min_closed_s": (0.0, 5.0),
    "open_before_s": (0.0, 3.0),
    "open_after_s": (0.0, 5.0),
}


class SilenceOptionError(EditError):
    """An option that is not a number."""


@dataclass(frozen=True)
class SilenceOptions:
    margin_db: float = grid.FLOOR_MARGIN_DB
    dominance_db: float = masks.DUCK_DOMINANCE_DB
    min_open_s: float = DEFAULT_MIN_OPEN_S
    min_closed_s: float = DEFAULT_MIN_CLOSED_S
    open_before_s: float = masks.DUCK_LOOKAHEAD
    open_after_s: float = masks.DUCK_HOLD
    method: str = "threshold"

    def as_dict(self) -> dict:
        return asdict(self)


def _number(name: str, value: object) -> float:
    if isinstance(value, bool):
        raise SilenceOptionError("error.silence.bad_option", name=name, value=str(value))
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise SilenceOptionError("error.silence.bad_option", name=name,
                                 value=str(value)) from None
    if not math.isfinite(number):
        raise SilenceOptionError("error.silence.bad_option", name=name, value=str(value))
    return number


def parse(args: dict | None) -> SilenceOptions:
    """The options in ``args`` (a command's arguments; other keys are
    ignored), defaults for what is missing or ``None``, numbers clamped."""
    args = args or {}
    given: dict[str, object] = {}
    for name, (low, high) in RANGES.items():
        if args.get(name) is None:
            continue
        given[name] = min(high, max(low, _number(name, args[name])))
    method = args.get("method")
    if method is not None:
        if method not in METHODS:
            raise SilenceOptionError("error.silence.bad_option", name="method",
                                     value=str(method))
        given["method"] = method
    return SilenceOptions(**given)  # type: ignore[arg-type]
