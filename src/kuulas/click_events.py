"""Click and smack candidates from short-time energy.

Find short runs of levels that jump up from the previous hop and then drop
back down. Pure Python, stdlib only: no imports from kuulas. Errors are plain
ValueError; there is no user-facing text.
"""

from __future__ import annotations


def find_clicks(levels_db: list[float], hop: int, jump_db: float,
                max_len: int, floor_db: float) -> list[tuple[int, int]]:
    """Return ``(start_frame, end_frame)`` click candidates.

    A click candidate is a run of 1 to ``max_len`` consecutive levels that each
    exceed the level of the hop just before the run by at least ``jump_db`` and
    are above ``floor_db``, followed by a drop back below the previous level
    plus ``jump_db / 2``. Frames are ``index * hop``; ``end_frame`` is one past
    the last level of the run. Results are sorted and non-overlapping.

    Raises ``ValueError`` for ``hop <= 0``, ``max_len < 1`` or ``jump_db <= 0``.
    An empty or single-level series returns ``[]``. The input is not mutated.
    """
    if hop <= 0:
        msg = f"hop ({hop}) must be > 0"
        raise ValueError(msg)
    if max_len < 1:
        msg = f"max_len ({max_len}) must be >= 1"
        raise ValueError(msg)
    if jump_db <= 0:
        msg = f"jump_db ({jump_db}) must be > 0"
        raise ValueError(msg)

    n = len(levels_db)
    if n < 2:
        return []

    clicks: list[tuple[int, int]] = []
    i = 1
    while i <= n - 2:
        prev = levels_db[i - 1]
        if (levels_db[i] >= prev + jump_db and levels_db[i] > floor_db):
            j = i
            while (j + 1 < n
                   and levels_db[j + 1] >= prev + jump_db
                   and levels_db[j + 1] > floor_db):
                j += 1
            run_len = j - i + 1
            if (run_len <= max_len and j + 1 < n
                    and levels_db[j + 1] < prev + jump_db / 2):
                clicks.append((i * hop, (j + 1) * hop))
                i = j + 2
                continue
            i = j + 1
        else:
            i += 1
    return clicks
