"""Statistics of one session (a project folder), WP70.

``compute`` is pure: it turns a project state, the timeline's words and the
steps of the history into one dictionary of numbers and never touches the
project. ``groups`` and ``to_text`` turn that dictionary into the words the
dialog, the command line and "Copy as text" all show (one formatter, so the
three never differ). ``gather`` reads what ``compute`` needs from a History.

What the history cannot tell is left out rather than guessed: an undo moves
the head and leaves no step behind, so there is no undo count; a
``cut_words`` step made before WP70 recorded no range, so its time is not in
"cut out" (``cut_unmeasured`` counts such steps).
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import package, transcript
from . import talk_share as talk_sharem
from .clip_gaps import clip_gaps
from .gate import split_by_gate
from .messages import t
from .model import Project
from .speech_stats import TURN_GAP_SECONDS, _speaker, speaker_stats
from .usage import UsageError, extract

#: Two steps further apart than this are not one stretch of work: a night
#: away must not count as editing time (the owner's rule, WP70).
ACTIVE_GAP_SECONDS = 10 * 60

#: The parts of the project folder the Size group shows, and what is linked in place.
SIZE_KEYS = ("project_bytes", "media_bytes", "recordings_folder_bytes", "history_bytes",
             "backups_bytes", "backups_count", "caches_bytes", "recordings_bytes")

#: Steps that remove a stretch of the timeline and say which, by op name. The
#: range is ``args["start"]``..``args["end"]`` in frames.
CUT_OPS = frozenset({"cut_range", "ripple_delete", "clipboard_cut", "cut_words"})

_KIND_OF = {
    "split": ("split_clip", "split_clips"),
    "cut": tuple(CUT_OPS),
    "delete": ("delete_clip", "delete_clips", "delete_track", "delete_empty_tracks",
               "delete_bus", "delete_marker", "delete_placeholder"),
    "move": ("move_clip", "move_clips_to_track", "shift_clips", "nudge_clips",
             "move_track", "move_marker", "move_placeholder"),
    "trim": ("trim_clip", "trim_clips", "roll_trim", "ripple_trim", "restore_cuts"),
    "gain": ("adjust_clip_gain", "set_master", "reset_gains", "match_loudness",
             "set_clip_envelope", "set_track_automation", "automix", "duck_music"),
    "mute": ("mute_range", "mute_ranges", "clipboard_lift_cut", "solo", "auto_silence",
             "set_gate", "add_gate_range", "remove_gate_range"),
    "fade": ("set_fade_at",),
    "marker": ("add_marker", "rename_marker", "set_region_end", "set_marker_kind"),
    "add": ("add_clip", "add_track", "add_bus", "add_media", "add_placeholder",
            "clipboard_paste", "replace_placeholder", "placeholder_take", "import_nhsx"),
    "group": ("group_clips", "ungroup_clips", "merge_clips", "mark_in_sync", "resync"),
}
_KIND = {op: kind for kind, ops_ in _KIND_OF.items() for op in ops_}
#: The generic setters are a gain or a mute change by what they set.
_SETTERS = frozenset({"set_clip", "set_clips", "set_track", "set_bus"})


def kind_of(name: str, args: dict) -> str:
    """The family of a step, for "steps by kind"."""
    if name in _SETTERS:
        fields = set(args)
        if fields & {"muted", "mute"}:
            return "mute"
        if "gain_db" in fields:
            return "gain"
        return "settings"
    return _KIND.get(name, "other")


def _seconds(frames: int | float, rate: int) -> float:
    return round(frames / rate, 3) if rate else 0.0


def _parse(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _audible(project: Project) -> list[tuple[str, str, int, int]]:
    """``(track, kind, start, end)`` of every audible stretch (usage.extract's
    rules: a muted clip or track, automation below -60 dB, a closed gate)."""
    try:
        return [(u.track, u.role, u.timeline_from, u.timeline_to)
                for u in extract(project) if u.audible]
    except UsageError:
        # A damaged excerpt chain: fall back to what the clips say themselves.
        silent = {tr.id for tr in project.tracks if tr.mute}
        return [(tr.id, tr.kind, c.start, c.end) for tr in project.tracks
                if tr.id not in silent for c in tr.clips if not c.muted]


def _root(project_media: dict, media_id: str) -> str:
    seen: set[str] = set()
    while media_id not in seen:
        seen.add(media_id)
        media = project_media.get(media_id)
        if media is None or not media.excerpt_of or media.excerpt_of == media_id:
            break
        media_id = media.excerpt_of
    return media_id


def _runtime(project: Project, steps: list[dict]) -> dict:
    audible = _audible(project)
    rate = project.rate
    cut = 0
    unmeasured = 0
    for s in steps:
        if s["name"] not in CUT_OPS:
            continue
        args = s["args"]
        try:
            cut += max(0, int(args["end"]) - int(args["start"]))
        except (KeyError, TypeError, ValueError):
            unmeasured += 1
    originals = sum(m.frames for m in project.media if not m.excerpt_of)
    return {
        "edit_seconds": _seconds(max((b for *_x, b in audible), default=0), rate),
        # The end of the last clip of any kind, muted or not: where the timeline
        # really stops, counted from time 0.
        "span_seconds": _seconds(max((c.end for tr in project.tracks
                                      for c in tr.clips), default=0), rate),
        "recordings_seconds": _seconds(originals, rate),
        "cut_seconds": _seconds(cut, rate),
        "cut_unmeasured": unmeasured,
    }


def _clip_muted(track, clip) -> int:
    """Frames of ``clip`` the mixer renders as silence because of the clip's own
    mute flag or the track's gate: the whole clip when it is muted, else the
    closed pieces of the gate inside it. A clip is looked at alone, so a stretch is
    never counted twice (a muted clip's gated part is just muted). Track mute and
    solo are not here: they are flags of the track, not muted time."""
    if clip.muted:
        return clip.end - clip.start
    return sum(b - a for a, b, is_open in split_by_gate(track.gate, clip.start, clip.end)
               if not is_open)


def _tracks(project: Project) -> list[dict]:
    """One row per track, in track order (WP70 rework)."""
    rate = project.rate
    soloing = any(tr.solo for tr in project.tracks)
    rows = []
    for tr in project.tracks:
        content = sum(c.end - c.start for c in tr.clips)
        muted = sum(_clip_muted(tr, c) for c in tr.clips)
        span = (max(c.end for c in tr.clips) - min(c.start for c in tr.clips)
                if tr.clips else 0)
        rows.append({
            "id": tr.id, "name": tr.name, "kind": tr.kind, "clips": len(tr.clips),
            "span_seconds": _seconds(span, rate),
            "content_seconds": _seconds(content, rate),
            "muted_seconds": _seconds(muted, rate),
            "audible_seconds": _seconds(content - muted, rate),
            # The mixer: while anything is soloed only soloed tracks are heard, muted
            # or not; otherwise a muted track is silent.
            "solo": bool(tr.solo),
            "track_muted": bool(tr.mute) and not soloing,
            "solo_silenced": soloing and not tr.solo,
        })
    return rows


def _counts(project: Project) -> dict:
    rate = project.rate
    by_id = {m.id: m for m in project.media}
    used = {_root(by_id, c.media) for tr in project.tracks for c in tr.clips}
    originals = {m.id for m in project.media if not m.excerpt_of}
    gaps = 0
    gap_frames = 0
    for tr in project.tracks:
        try:
            found = clip_gaps([(c.start, c.end) for c in tr.clips])["gaps"]
        except ValueError:
            continue  # a clip of no length: nothing sensible to say of this track
        gaps += len(found)
        gap_frames += sum(b - a for a, b in found)
    clips = [c for tr in project.tracks for c in tr.clips]
    lengths = [c.end - c.start for c in clips]
    return {
        "clip_lengths": {
            "longest_seconds": _seconds(max(lengths, default=0), rate),
            "shortest_seconds": _seconds(min(lengths, default=0), rate),
            "average_seconds": _seconds(
                sum(lengths) / len(lengths) if lengths else 0, rate),
        },
        "tracks": len(project.tracks),
        "speech_tracks": sum(tr.kind == "speech" for tr in project.tracks),
        "music_tracks": sum(tr.kind == "music" for tr in project.tracks),
        "buses": len(project.buses),
        "clips": len(clips),
        "clips_per_track": [{"id": tr.id, "name": tr.name, "clips": len(tr.clips)}
                            for tr in project.tracks],
        "recordings_used": len(used & originals),
        "recordings_unused": len(originals - used),
        "markers": sum(m.kind == "marker" for m in project.markers),
        "chapters": sum(m.kind == "chapter" for m in project.markers),
        "regions": sum(m.kind == "region" for m in project.markers),
        "gaps": gaps,
        "gap_seconds": _seconds(gap_frames, rate),
        "groups": len({c.group for c in clips if c.group}),
        "sync_groups": len(project.sync_groups),
        "muted_clips": sum(c.muted for c in clips),
    }


def _talk(project: Project, words: list[dict], names: dict[str, str]) -> dict | None:
    rate = project.rate
    heard = sorted((w for w in words if not w.get("muted") and w["e"] > w["s"]),
                   key=lambda w: (w["s"], w["track"]))
    if not heard:
        return None
    stats = speaker_stats(heard, rate=rate)
    # Longest stretch: the longest run one speaker keeps going, by the same turn
    # rule as speech_stats (a change of speaker, or a pause over TURN_GAP_SECONDS).
    longest: dict[str, float] = {}
    run_start = prev = None
    for w in heard:
        who = _speaker(w)
        new = prev is None or _speaker(prev) != who or (
            (w["s"] - prev["e"]) / rate > TURN_GAP_SECONDS)
        if new and prev is not None:
            who_prev = _speaker(prev)
            length = (prev["e"] - run_start) / rate
            longest[who_prev] = max(longest.get(who_prev, 0.0), length)
        if new:
            run_start = w["s"]
        prev = w
    who_prev = _speaker(prev)
    longest[who_prev] = max(longest.get(who_prev, 0.0), (prev["e"] - run_start) / rate)

    ranges: dict[str, list[tuple[int, int]]] = {}
    for w in heard:
        ranges.setdefault(_speaker(w), []).append((w["s"], w["e"]))
    overlap = talk_sharem.talk_share(ranges)["overlap"]
    total = sum(float(v["seconds"]) for v in stats.values())
    speakers = [{
        "key": key,
        "name": names.get(key, key),
        "seconds": round(float(v["seconds"]), 3),
        "share": float(v["seconds"]) / total if total else 0.0,
        "turns": int(v["turns"]),
        "words": int(v["words"]),
        "longest_seconds": round(longest.get(key, 0.0), 3),
    } for key, v in stats.items()]
    speakers.sort(key=lambda s: (-s["seconds"], s["key"]))
    return {"speakers": speakers, "words": len(heard),
            "overlap_seconds": _seconds(int(overlap), rate)}


def _work(steps: list[dict], checkpoints: list[dict], now: datetime) -> dict:
    edits = [s for s in steps if s["name"] and s["name"] != "marker"]
    kinds: dict[str, int] = {}
    for s in edits:
        kind = kind_of(s["name"], s["args"])
        kinds[kind] = kinds.get(kind, 0) + 1
    times = sorted(_parse(s["created"]) for s in edits)
    active = sum(gap for a, b in pairwise(times)
                 if (gap := (b - a).total_seconds()) < ACTIVE_GAP_SECONDS)
    exports = sorted(c["created_utc"] for c in checkpoints if c["kind"] == "export")
    last_export = exports[-1] if exports else None
    return {
        "steps": len(edits),
        "by_kind": dict(sorted(kinds.items(), key=lambda kv: (-kv[1], kv[0]))),
        "versions": sum(c["kind"] != "export" for c in checkpoints),
        "exports": len(exports),
        "first_edit": edits[0]["created"] if edits else None,
        "last_edit": edits[-1]["created"] if edits else None,
        "active_seconds": active,
        "last_export": last_export,
        "since_export_seconds": (max(0.0, (now - _parse(last_export)).total_seconds())
                                 if last_export else None),
    }


def compute(project: Project, *, words: list[dict] | None = None,
            steps: Iterable[dict] = (), checkpoints: Iterable[dict] = (),
            sizes: dict[str, int] | None = None, names: dict[str, str] | None = None,
            now: datetime | None = None) -> dict:
    """The statistics of one session as a dictionary (see the module docs).

    ``words``: the timeline's words (``transcript.timeline_words``), or None
    when there is no transcript (the ``talk`` key is then absent). ``steps``:
    ``History.story`` steps, oldest first; ``checkpoints`` likewise. ``names``
    maps a speaker key (person id, label or track id) to a display name.
    """
    now = now or datetime.now(UTC)
    steps = list(steps)
    names = {**{tr.id: tr.name for tr in project.tracks}, **(names or {})}
    out = {
        "runtime": _runtime(project, [s for s in steps if s["name"]]),
        "tracks": _tracks(project),
        "counts": _counts(project),
    }
    talk = _talk(project, words, names) if words else None
    if talk is not None:
        out["talk"] = talk
    out["work"] = _work(steps, list(checkpoints), now)
    size = sizes or {}
    out["size"] = {key: int(size.get(key, 0)) for key in SIZE_KEYS}
    return out


# -- reading a History ----------------------------------------------------------


def _folder_bytes(folder: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue  # gone while we looked
    return total


def _file_bytes(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def gather(history, folder: str | Path | None = None, *,
           lock: AbstractContextManager | None = None, transcripts=None,
           now: datetime | None = None) -> dict:
    """Read what ``compute`` needs from ``history`` and compute.

    Only the snapshot (state, words, people, media rows) is taken under
    ``lock``; the steps are read on a connection of their own and the
    arithmetic and the folder sizes run with the lock released.
    ``transcripts``: a callable giving media id -> words (a Session passes its
    memoized one); default ``history.resolved_transcripts``.
    """
    with lock or nullcontext():
        state = history.state
        head = history.head
        words_by_media = (transcripts or history.resolved_transcripts)()
        people = {p.id: p.name for p in history.people()}
        media_rows = history.media_rows()
    steps, checkpoints = history.story(head)
    words = transcript.timeline_words(state, words_by_media) if words_by_media else None
    sizes: dict[str, int] = {}
    if folder is not None:
        folder = Path(folder)
        sizes["project_bytes"] = _folder_bytes(folder)
        for key, name in (("caches_bytes", "caches"), ("media_bytes", "media"),
                          ("recordings_folder_bytes", "recordings"),
                          ("backups_bytes", "backups")):
            sizes[key] = _folder_bytes(folder / name) if (folder / name).is_dir() else 0
        sizes["history_bytes"] = sum(_file_bytes(folder / f"project.sqlite{suffix}")
                                     for suffix in ("", "-wal"))
        sizes["backups_count"] = len(package.auto_backups(folder / "backups"))
        sizes["recordings_bytes"] = sum(int(r.get("linked_size") or 0)
                                        for r in media_rows if r["storage"] == "linked")
    return compute(state, words=words, steps=steps, checkpoints=checkpoints,
                   sizes=sizes, names=people, now=now)


# -- words ------------------------------------------------------------------------

HELSINKI = ZoneInfo("Europe/Helsinki")


def duration(seconds: float) -> str:
    """``1 h 05 min``, ``12 min 30 s`` or ``45 s``: whole seconds."""
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return t("stats.fmt.h_min", hours=hours, minutes=f"{minutes:02d}")
    if minutes:
        return t("stats.fmt.min_s", minutes=minutes, seconds=secs)
    return t("stats.fmt.s", seconds=secs)


def duration_ms(seconds: float) -> str:
    """``2:05.500`` or ``1:05:03.250``: the timeline's h:mm:ss.mmm clock."""
    whole, millis = divmod(round(seconds * 1000), 1000)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    head = f"{hours}:{minutes:02d}" if hours else str(minutes)
    return f"{head}:{secs:02d}{t('stats.fmt.point')}{millis:03d}"


def _track_row(r: dict) -> list[str]:
    flags = []
    if r["track_muted"]:
        flags.append(t("stats.tracks.flag_muted"))
    if r["solo_silenced"]:
        flags.append(t("stats.tracks.flag_solo_silenced"))
    if r["solo"]:
        flags.append(t("stats.tracks.flag_solo"))
    return [r["name"] or r["id"], t(f"stats.tracks.kind_{r['kind']}"), str(r["clips"]),
            duration_ms(r["span_seconds"]), duration_ms(r["content_seconds"]),
            duration_ms(r["muted_seconds"]), duration_ms(r["audible_seconds"]),
            ", ".join(flags)]


def size_text(n: int) -> str:
    if n >= 1_000_000_000:
        return t("stats.fmt.gb", value=f"{n / 1e9:.1f}")
    return t("stats.fmt.mb", value=f"{n / 1e6:.1f}")


def moment(utc_text: str) -> str:
    """A time with its zone: ``19.10.2026 13.05 Helsinki (10:05 UTC)``."""
    when = _parse(utc_text)
    local = when.astimezone(HELSINKI)
    return t("stats.fmt.moment", date=f"{local.day}.{local.month}.{local.year}",
             time=local.strftime("%H.%M"), utc=when.strftime("%H:%M"))


def _percent(share: float) -> str:
    return f"{share * 100:.0f} %"


def groups(stats: dict) -> list[dict]:
    """``[{"title", "rows": [[label, value], ...]}]``, in the language of the moment."""
    run, c, work, size = stats["runtime"], stats["counts"], stats["work"], stats["size"]
    out = []

    rows = [
        [t("stats.runtime.edit"), duration(run["edit_seconds"])],
        *([[t("stats.runtime.span"), duration(run["span_seconds"])]]
          if run["span_seconds"] != run["edit_seconds"] else []),
        [t("stats.runtime.recordings"), duration(run["recordings_seconds"])],
        [t("stats.runtime.cut"), duration(run["cut_seconds"])],
    ]
    if run["cut_unmeasured"]:
        rows.append([t("stats.runtime.cut_unmeasured"), str(run["cut_unmeasured"])])
    out.append({"title": t("stats.group.runtime"), "rows": rows})

    if stats["tracks"]:
        keys = ("name", "kind", "clips", "span", "content", "muted", "audible", "flags")
        out.append({"title": t("stats.group.tracks"), "rows": [], "table": {
            "head": [t(f"stats.tracks.{k}") for k in keys],
            "rows": [_track_row(r) for r in stats["tracks"]],
        }})

    rows = [
        [t("stats.counts.tracks"), t("stats.counts.tracks_value", total=c["tracks"],
                                     speech=c["speech_tracks"], music=c["music_tracks"])],
        [t("stats.counts.buses"), str(c["buses"])],
        [t("stats.counts.clips"), str(c["clips"])],
        *([t(f"stats.counts.clip_{k}"), duration_ms(c["clip_lengths"][f"{k}_seconds"])]
          for k in ("longest", "shortest", "average")),
        [t("stats.counts.recordings"), t("stats.counts.recordings_value",
                                         used=c["recordings_used"],
                                         unused=c["recordings_unused"])],
        [t("stats.counts.markers"), str(c["markers"])],
        [t("stats.counts.chapters"), str(c["chapters"])],
        [t("stats.counts.regions"), str(c["regions"])],
        [t("stats.counts.gaps"), t("stats.counts.gaps_value", count=c["gaps"],
                                   time=duration(c["gap_seconds"]))],
        [t("stats.counts.groups"), str(c["groups"])],
        [t("stats.counts.muted"), str(c["muted_clips"])],
    ]
    out.append({"title": t("stats.group.counts"), "rows": rows})

    talk = stats.get("talk")
    if talk:
        rows = [[s["name"], t("stats.talk.speaker_value", time=duration(s["seconds"]),
                              share=_percent(s["share"]), turns=s["turns"],
                              words=s["words"], longest=duration(s["longest_seconds"]))]
                for s in talk["speakers"]]
        rows.append([t("stats.talk.overlap"), duration(talk["overlap_seconds"])])
        out.append({"title": t("stats.group.talk"), "rows": rows})

    rows = [[t("stats.work.steps"), str(work["steps"])]]
    rows += [[t(f"stats.kind.{kind}"), str(n)] for kind, n in work["by_kind"].items()]
    rows += [
        [t("stats.work.versions"), str(work["versions"])],
        [t("stats.work.exports"), str(work["exports"])],
        [t("stats.work.active"), duration(work["active_seconds"])],
    ]
    if work["first_edit"]:
        rows.append([t("stats.work.first"), moment(work["first_edit"])])
        rows.append([t("stats.work.last"), moment(work["last_edit"])])
    if work["since_export_seconds"] is not None:
        rows.append([t("stats.work.since_export"),
                     duration(work["since_export_seconds"])])
    out.append({"title": t("stats.group.work"), "rows": rows})

    # [label, value, hint]: the dialog shows the hint, the text leaves it out.
    out.append({"title": t("stats.group.size"), "rows": [
        [t("stats.size.project"), size_text(size["project_bytes"]),
         t("stats.size.project_hint")],
        [t("stats.size.media"), size_text(size["media_bytes"]),
         t("stats.size.media_hint")],
        [t("stats.size.recordings_folder"), size_text(size["recordings_folder_bytes"]),
         t("stats.size.recordings_folder_hint")],
        [t("stats.size.history"), size_text(size["history_bytes"]),
         t("stats.size.history_hint")],
        [t("stats.size.backups"), t("stats.size.backups_value",
                                    count=size["backups_count"],
                                    size=size_text(size["backups_bytes"])),
         t("stats.size.backups_hint")],
        [t("stats.size.caches"), size_text(size["caches_bytes"]),
         t("stats.size.caches_hint")],
        [t("stats.size.recordings"), size_text(size["recordings_bytes"]),
         t("stats.size.recordings_hint")],
    ]})
    return out


def to_text(stats: dict, title: str | None = None) -> str:
    """The statistics as plain text: a heading per group, one line per number."""
    lines = [title] if title else []
    for group in groups(stats):
        if lines:
            lines.append("")
        lines.append(group["title"])
        lines.extend(f"  {row[0]}: {row[1]}" for row in group["rows"])
        table = group.get("table")
        if table:
            for row in table["rows"]:
                cells = [f"{h}: {v}" for h, v
                         in zip(table["head"][1:], row[1:], strict=True) if v]
                lines.append(f"  {row[0]}: " + "; ".join(cells))
    return "\n".join(lines) + "\n"


def describe(stats: dict) -> dict[str, Any]:
    """What the API answers: the numbers, the groups, and the text."""
    return {"stats": stats, "groups": groups(stats), "text": to_text(stats)}
