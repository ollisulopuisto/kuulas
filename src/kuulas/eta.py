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
