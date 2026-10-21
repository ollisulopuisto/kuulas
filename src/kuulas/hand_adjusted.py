"""Hand-adjusted speech levels and the balance cap for the automixer.

``hand_adjusted`` reports whether any speech track (or any of its non-muted
clips, or any envelope point on them) carries a gain beyond a tiny threshold.
Music tracks and muted tracks or clips never count. ``balance_cap`` returns
the largest dB the automixer may move a speaker based on that result.
Errors are plain ``ValueError``; there is no user-facing text.
"""

from __future__ import annotations

THRESHOLD_DB = 0.05
HAND_ADJUSTED_CAP_DB = 2.5
DEFAULT_CAP_DB = 6.0


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def hand_adjusted(tracks: list) -> bool:
    """Return True when a non-muted speech track or clip is hand-adjusted."""
    if not isinstance(tracks, list):
        msg = f"tracks must be a list, got {tracks!r}"
        raise ValueError(msg)  # noqa: TRY004 - the spec pins ValueError
    for track in tracks:
        if not isinstance(track, dict):
            continue
        if track.get("kind") != "speech":
            continue
        if track.get("mute") is True:
            continue
        if _is_number(track.get("gain_db")) and abs(track["gain_db"]) > THRESHOLD_DB:
            return True
        for clip in track.get("clips", []) or []:
            if not isinstance(clip, dict):
                continue
            if clip.get("muted") is True:
                continue
            if _is_number(clip.get("gain_db")) and abs(clip["gain_db"]) > THRESHOLD_DB:
                return True
            for point in clip.get("envelope", []) or []:
                if (isinstance(point, (list, tuple)) and len(point) == 2
                        and _is_number(point[1])
                        and abs(point[1]) > THRESHOLD_DB):
                    return True
    return False


def balance_cap(tracks: list, keep: bool = False) -> float:
    """Return the balance cap in dB for a speaker.

    ``keep`` true means 0.0; otherwise 2.5 when the project was hand-adjusted,
    else 6.0.
    """
    if not isinstance(tracks, list):
        msg = f"tracks must be a list, got {tracks!r}"
        raise ValueError(msg)  # noqa: TRY004 - the spec pins ValueError
    if keep:
        return 0.0
    return HAND_ADJUSTED_CAP_DB if hand_adjusted(tracks) else DEFAULT_CAP_DB
