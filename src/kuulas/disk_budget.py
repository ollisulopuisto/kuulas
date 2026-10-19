"""Disk budget: how much recording time is left on the disk.

``bytes_per_second``, ``seconds_left``, ``disk_state`` and ``format_hm``
compute the recording budget from free disk space. Errors are plain
``ValueError``; there is no user-facing text.
"""

from __future__ import annotations


def bytes_per_second(rate: int, channels: int, bytes_per_sample: int) -> int:
    """Return bytes per second of recording: rate * channels * bytes_per_sample."""
    if rate <= 0:
        msg = f"rate must be positive, got {rate}"
        raise ValueError(msg)
    if channels <= 0:
        msg = f"channels must be positive, got {channels}"
        raise ValueError(msg)
    if bytes_per_sample <= 0:
        msg = f"bytes_per_sample must be positive, got {bytes_per_sample}"
        raise ValueError(msg)
    return rate * channels * bytes_per_sample


def seconds_left(
    free_bytes: int,
    rate: int,
    channels: int,
    bytes_per_sample: int,
    reserve_bytes: int = 500_000_000,
) -> int:
    """Return whole seconds of recording that fit in ``free_bytes - reserve_bytes``.

    The result is never negative: a reserve larger than the free space yields 0.
    """
    if free_bytes < 0:
        msg = f"free_bytes must not be negative, got {free_bytes}"
        raise ValueError(msg)
    if reserve_bytes < 0:
        msg = f"reserve_bytes must not be negative, got {reserve_bytes}"
        raise ValueError(msg)
    bps = bytes_per_second(rate, channels, bytes_per_sample)
    available = free_bytes - reserve_bytes
    if available <= 0:
        return 0
    return available // bps


def disk_state(seconds_left_value: int, warn_s: int = 1800, critical_s: int = 300) -> str:
    """Return ``"ok"``, ``"warn"``, ``"critical"`` or ``"full"`` for seconds left.

    ``0`` is ``"full"``; at or below ``critical_s`` is ``"critical"``; at most
    ``warn_s`` (and above ``critical_s``) is ``"warn"``; above ``warn_s`` is
    ``"ok"``. Both boundaries belong to the nearer state.
    """
    if seconds_left_value == 0:
        return "full"
    if seconds_left_value <= critical_s:
        return "critical"
    if seconds_left_value <= warn_s:
        return "warn"
    return "ok"


def format_hm(seconds: float) -> str:
    """Return ``"H:MM"`` at or above an hour and ``"M:SS"`` below it.

    Seconds are floored; a negative value raises ``ValueError``.
    """
    if seconds < 0:
        msg = f"seconds must not be negative, got {seconds}"
        raise ValueError(msg)
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}"
    return f"{minutes}:{secs:02d}"
