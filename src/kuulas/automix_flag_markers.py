"""Convert parsed automixer flags into marker plans (T68)."""

from typing import Any


def flag_markers(
    flags: list[dict[str, Any]],
    rate: int,
    *,
    min_abs_db: float = 3.0,
    include_loud: bool = True,
    merge_gap_s: float = 2.0,
) -> list[dict[str, Any]]:
    """Convert parsed automixer flags into timeline marker plan dicts.

    Args:
        flags: list of dicts from automixer flag parser.
        rate: project sample rate in Hz.
        min_abs_db: minimum absolute off_db threshold to keep a flag.
        include_loud: whether to include 'loud' kind flags.
        merge_gap_s: max start time difference from marker start to merge into it.

    Returns:
        List of dicts with frame, end_frame, names, kinds, worst_db, count.
    """
    if not flags:
        return []

    kept = [
        f
        for f in flags
        if abs(f["off_db"]) >= min_abs_db and (include_loud or f["kind"] != "loud")
    ]
    if not kept:
        return []

    kept.sort(key=lambda f: f["start_s"])

    markers: list[dict[str, Any]] = []

    cur_start_s: float | None = None
    cur_end_s: float = 0.0
    cur_names: list[str] = []
    cur_kinds: set[str] = set()
    cur_worst_db: float = 0.0
    cur_count: int = 0

    for f in kept:
        f_start = f["start_s"]
        f_end = f["end_s"]
        f_name = f["name"]
        f_kind = f["kind"]
        f_off = f["off_db"]

        if cur_start_s is None or (f_start - cur_start_s) > merge_gap_s:
            if cur_start_s is not None:
                markers.append(
                    {
                        "frame": round(cur_start_s * rate),
                        "end_frame": round(cur_end_s * rate),
                        "names": cur_names,
                        "kinds": sorted(cur_kinds),
                        "worst_db": float(cur_worst_db),
                        "count": cur_count,
                    }
                )
            cur_start_s = f_start
            cur_end_s = f_end
            cur_names = [f_name]
            cur_kinds = {f_kind}
            cur_worst_db = f_off
            cur_count = 1
        else:
            cur_end_s = max(cur_end_s, f_end)
            if f_name not in cur_names:
                cur_names.append(f_name)
            cur_kinds.add(f_kind)
            if abs(f_off) > abs(cur_worst_db):
                cur_worst_db = f_off
            cur_count += 1

    if cur_start_s is not None:
        markers.append(
            {
                "frame": round(cur_start_s * rate),
                "end_frame": round(cur_end_s * rate),
                "names": cur_names,
                "kinds": sorted(cur_kinds),
                "worst_db": float(cur_worst_db),
                "count": cur_count,
            }
        )

    return markers
