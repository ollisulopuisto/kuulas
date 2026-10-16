"""The recording clock: flicks.

A flick is 1/705 600 000 s. Every audio rate (8k to 192k, 44.1k and its
multiples included) and every video frame rate, 29.97 too, divides it
exactly, so a position on a recording's clock never rounds when it is
stored, and never changes when the project rate changes (docs/FORMAT.md).

Edits stay in project frames; recording facts (sync origins, BWF start
times, transcript words) are in flicks and are converted at the edges.
"""

from __future__ import annotations

from .messages import KuulasError

#: 2^9 * 3^2 * 5^5 * 7^2: divisible by every common audio rate and by the
#: video rates (24, 25, 30, 48, 50, 60 and the NTSC ones x 1000/1001 per frame).
FLICKS = 705_600_000


class RateError(KuulasError, ValueError):
    """A sample rate whose samples are not a whole number of flicks."""


def check_rate(rate: int) -> None:
    """Refuse a rate the recording clock cannot hold exactly.

    Every rate kuulas meets in practice (8k to 192k, the 44.1k family
    included) divides ``FLICKS``. One that does not (e.g. 37.8 kHz) would
    make sync origins and BWF times round, so it is refused at import.
    """
    if int(rate) <= 0 or FLICKS % int(rate):
        raise RateError("error.clock.rate", rate=rate)


def frames_to_flicks(frames: int, rate: int) -> int:
    """Exact when ``rate`` divides ``FLICKS`` (every rate ``check_rate``
    accepts); otherwise the nearest flick, half to even."""
    return _div_half_even(int(frames) * FLICKS, int(rate))


def flicks_to_frames(flicks: int, rate: int) -> int:
    """The nearest frame; a position exactly between two goes to the even
    one (round half to even), so converting back and forth cannot drift in
    one direction."""
    return _div_half_even(int(flicks) * int(rate), FLICKS)


def _div_half_even(num: int, den: int) -> int:
    q, r = divmod(num, den)
    twice = 2 * r
    if twice > den or (twice == den and q % 2):
        q += 1
    return q
