"""Estimate the time left of a long job."""


def remaining_seconds(samples):
    """Return whole seconds remaining, or None when too early to say.

    ``samples`` is a list of ``(seconds_since_start, fraction)`` pairs in time
    order. A fraction that drops below the largest earlier fraction is ignored.
    """
    result = None
    if len(samples) >= 3:
        kept = []
        max_fraction = -1.0
        for t, f in samples:
            if f >= max_fraction:
                kept.append((t, f))
                max_fraction = f

        newest_t, newest_f = kept[-1]

        if 0.05 <= newest_f < 1.0:
            # Stuck: no growth since a sample at least 30 s older than the newest (the
            # bar moves in jumps, so the window may hold only the newest sample).
            reference = None
            for t, f in kept:
                if t <= newest_t - 30.0:
                    reference = f
            if reference is None or reference != newest_f:
                # Speed over the last 60 s: from the newest sample at least 60 s old,
                # else from the first sample.
                base_t, base_f = kept[0]
                for t, f in kept:
                    if t <= newest_t - 60.0:
                        base_t, base_f = t, f
                dt = newest_t - base_t
                speed = (newest_f - base_f) / dt if dt > 0 else 0.0
                if speed > 0:
                    result = max(0, round((1.0 - newest_f) / speed))
        elif newest_f >= 1.0:
            result = 0
    return result


class EtaSampler:
    """Collect progress samples, keeping only those where the bar grew."""

    def __init__(self):
        self._samples = []

    def add(self, seconds_since_start, fraction):
        """Keep the sample only if the fraction grew and the clock moved on."""
        if not 0.0 <= fraction <= 1.0:
            return
        if self._samples and seconds_since_start < self._samples[-1][0]:
            return
        if self._samples and fraction <= self._samples[-1][1]:
            return
        self._samples.append((seconds_since_start, fraction))
        if len(self._samples) > 200:
            self._samples.pop(0)

    def samples(self):
        """Return a copy of the kept ``(t, f)`` samples."""
        return list(self._samples)

    def estimate(self):
        """Return ``remaining_seconds`` over the kept samples."""
        return remaining_seconds(self.samples())


def remaining_parts(seconds):
    """Split a remaining-seconds estimate into a unit and a number.

    Returns ``None`` for ``None``, ``("under_minute", 0)`` below 60 s,
    ``("minutes", n)`` up to 90 minutes, else ``("hours_minutes", (h, m))``.
    """
    if seconds is None:
        return None
    if seconds < 60:
        return ("under_minute", 0)
    if seconds <= 90 * 60:
        return ("minutes", round(seconds / 60))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return ("hours_minutes", (hours, minutes))


def format_remaining(seconds):
    """Return a plain English estimate string for ``seconds`` or ``""`` for None."""
    if seconds is None:
        return ""
    if seconds < 60:
        return "under a minute"
    if seconds <= 90 * 60:
        return f"about {round(seconds / 60)} min"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"about {hours} h {minutes} min"
