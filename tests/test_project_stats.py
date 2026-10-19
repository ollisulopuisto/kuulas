"""WP70: session statistics. Pure numbers from a project, its words and its history."""

import json
import threading
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from test_history import heavy_hour, register

from kuulas import cli, messages, ops, project_stats
from kuulas.clock import FLICKS
from kuulas.model import Media, Project
from kuulas.server import create_app
from kuulas.session import Session

R = 48000


def sec(n: float) -> int:
    return int(n * R)


def build() -> Project:
    """Known counts. Speech t1 (Host): a 0-10 s, then b 12-20 s. Speech t2 (Guest):
    b 0-6 s and a muted b clip at 10-14 s. Music tm: one clip 0-30 s. Media c (5 s) is
    never used."""
    p = Project(rate=R)
    for mid, name, secs in (("ma", "a.wav", 10), ("mb", "b.wav", 20),
                            ("mc", "c.wav", 5), ("mm", "music.wav", 40)):
        p = ops.add_media(p, Media(id=mid, name=name, channels=1, frames=sec(secs),
                                   sha256=mid * 32))
    p = ops.add_track(p, track_id="t1", name="Host")
    p = ops.add_track(p, track_id="t2", name="Guest")
    p = ops.add_track(p, track_id="tm", name="Music", kind="music")
    p = ops.add_bus(p, bus_id="b1", name="Speech bus")
    p = ops.add_clip(p, "t1", "ma", start=0, clip_id="c1")
    p = ops.add_clip(p, "t1", "mb", start=sec(12), length=sec(8), clip_id="c2")
    p = ops.add_clip(p, "t2", "mb", start=0, length=sec(6), clip_id="c3")
    p = ops.add_clip(p, "t2", "mb", start=sec(10), length=sec(4), clip_id="c4")
    p = ops.set_clip(p, "c4", muted=True)
    p = ops.add_clip(p, "tm", "mm", start=0, length=sec(30), clip_id="c5")
    p = ops.group_clips(p, ["c1", "c3"])
    p = ops.add_marker(p, "k1", "Intro", sec(1))
    p = ops.add_marker(p, "k2", "Part", sec(2), kind="chapter")
    return ops.add_marker(p, "k3", "Quote", sec(3), end=sec(5), kind="region")


def w(word, s, e, track, spk="", person="", muted=False):
    return {"w": word, "s": sec(s), "e": sec(e), "track": track, "spk": spk,
            "person": person, "muted": muted}


WORDS = [
    w("hello", 0.0, 1.0, "t1", person="p1"),
    w("there", 1.0, 2.0, "t1", person="p1"),
    w("hi", 2.5, 3.5, "t2", person="p2"),     # speaker change: a new turn
    w("again", 3.0, 4.0, "t1", person="p1"),  # overlaps "hi" by 0.5 s
    w("muted", 4.0, 9.0, "t2", person="p2", muted=True),
]


def test_runtime_counts_and_sizes():
    s = project_stats.compute(build(), sizes={"project_bytes": 10, "recordings_bytes": 20,
                                              "caches_bytes": 3})
    run = s["runtime"]
    # The music clip ends last (30 s) and is audible.
    assert run["edit_seconds"] == 30.0
    # The span from 0 to the end of the last clip of any kind is also 30 s here.
    assert run["span_seconds"] == 30.0
    assert "speech_seconds" not in run  # replaced by the per-track table (WP70 rework)
    # Recordings imported: 10 + 20 + 5 + 40 seconds.
    assert run["recordings_seconds"] == 75.0
    assert run["cut_seconds"] == 0.0
    c = s["counts"]
    assert (c["tracks"], c["speech_tracks"], c["music_tracks"]) == (3, 2, 1)
    assert c["buses"] == 1
    assert c["clips"] == 5
    assert c["clips_per_track"] == [{"id": "t1", "name": "Host", "clips": 2},
                                    {"id": "t2", "name": "Guest", "clips": 2},
                                    {"id": "tm", "name": "Music", "clips": 1}]
    assert (c["recordings_used"], c["recordings_unused"]) == (3, 1)
    assert (c["markers"], c["regions"], c["chapters"]) == (1, 1, 1)
    assert c["muted_clips"] == 1
    assert c["groups"] == 1
    # Gaps between clips: t1 10-12 s, t2 6-10 s (2 gaps, 6 s).
    assert (c["gaps"], c["gap_seconds"]) == (2, 6.0)
    assert s["size"] == {"project_bytes": 10, "recordings_bytes": 20, "caches_bytes": 3}


def test_a_muted_track_is_not_audible_in_the_runtime():
    p = ops.set_track(build(), "tm", mute=True)
    assert project_stats.compute(p)["runtime"]["edit_seconds"] == 20.0


def rows(s):
    return {r["id"]: r for r in s["tracks"]}


def test_track_table_span_content_muted_audible():
    r = rows(project_stats.compute(build()))
    ids = [x["id"] for x in project_stats.compute(build())["tracks"]]
    assert ids == ["t1", "t2", "tm"]
    # Host: clips 0-10 and 12-20. The span runs from the first start to the last end,
    # the content is the sum of the clip lengths (the 2 s hole is in neither the
    # content nor the muted time).
    assert (r["t1"]["name"], r["t1"]["kind"], r["t1"]["clips"]) == ("Host", "speech", 2)
    assert (r["t1"]["span_seconds"], r["t1"]["content_seconds"]) == (20.0, 18.0)
    assert (r["t1"]["muted_seconds"], r["t1"]["audible_seconds"]) == (0.0, 18.0)
    # Guest: 0-6 and a muted 10-14: the muted clip's whole length is muted time.
    assert (r["t2"]["span_seconds"], r["t2"]["content_seconds"]) == (14.0, 10.0)
    assert (r["t2"]["muted_seconds"], r["t2"]["audible_seconds"]) == (4.0, 6.0)
    assert r["tm"]["kind"] == "music"
    assert (r["tm"]["span_seconds"], r["tm"]["audible_seconds"]) == (30.0, 30.0)


def test_gate_closed_time_counts_as_muted_once():
    p = build()
    # Closed 2-4 s and 11-14 s on Host: 2-4 lies in c1 (2 s), 12-14 in c2 (2 s); the
    # 11-12 s hole is no clip. On Guest the gate 3-12 s overlaps the muted clip c4
    # (10-12): that part must not be counted twice (it is muted already).
    p = ops.set_gate(p, "t1", [(sec(2), sec(4)), (sec(11), sec(14))])
    p = ops.set_gate(p, "t2", [(sec(3), sec(12))])
    r = rows(project_stats.compute(p))
    assert r["t1"]["muted_seconds"] == 4.0
    assert r["t1"]["audible_seconds"] == 14.0
    # c3 (0-6): closed 3-6 = 3 s; c4 (10-14) is muted whole = 4 s, not 4 + 2.
    assert r["t2"]["muted_seconds"] == 7.0
    assert r["t2"]["audible_seconds"] == 3.0
    t2 = r["t2"]
    assert t2["muted_seconds"] + t2["audible_seconds"] == t2["content_seconds"]


def test_track_mute_and_solo_are_flags_not_muted_time():
    p = ops.set_track(build(), "t1", mute=True)
    r = rows(project_stats.compute(p))
    assert r["t1"]["track_muted"] is True
    assert (r["t1"]["muted_seconds"], r["t1"]["audible_seconds"]) == (0.0, 18.0)
    assert (r["t2"]["track_muted"], r["t2"]["solo_silenced"]) == (False, False)
    # While tm is soloed the others are silenced by the solo, and a muted track that
    # is itself soloed is heard (the mixer's rule: solo overrides mute).
    p = ops.set_track(p, "tm", solo=True)
    r = rows(project_stats.compute(p))
    assert (r["t1"]["solo_silenced"], r["t2"]["solo_silenced"]) == (True, True)
    assert (r["tm"]["solo_silenced"], r["tm"]["solo"]) == (False, True)
    p = ops.set_track(p, "t1", solo=True)
    r = rows(project_stats.compute(p))
    assert (r["t1"]["track_muted"], r["t1"]["solo_silenced"]) == (False, False)


def test_clip_length_extremes_and_span_when_the_last_clip_is_muted():
    s = project_stats.compute(build())
    cl = s["counts"]["clip_lengths"]
    # Clips: 10, 8, 6, 4 and 30 s.
    assert (cl["longest_seconds"], cl["shortest_seconds"]) == (30.0, 4.0)
    assert cl["average_seconds"] == pytest.approx(11.6)
    p = ops.add_clip(build(), "t1", "mm", start=sec(32), length=sec(5), clip_id="c9")
    p = ops.set_clip(p, "c9", muted=True)
    run = project_stats.compute(p)["runtime"]
    assert run["edit_seconds"] == 30.0
    assert run["span_seconds"] == 37.0


def test_tracks_in_the_words_and_the_text():
    s = project_stats.compute(ops.set_track(build(), "t1", mute=True))
    text = project_stats.to_text(s)
    assert all(word in text for word in ("Session duration", "Host", "Guest"))
    table = next(g for g in project_stats.groups(s) if g.get("table"))
    assert len(table["table"]["rows"]) == 3
    assert len(table["table"]["head"]) == len(table["table"]["rows"][0])
    messages.set_language("fi")
    assert "Istunnon kesto" in project_stats.to_text(s)


def test_talk_section_per_speaker():
    s = project_stats.compute(build(), words=WORDS, names={"p1": "Anna", "p2": "Ben"})
    talk = s["talk"]
    by = {x["key"]: x for x in talk["speakers"]}
    assert by["p1"]["name"] == "Anna"
    assert (by["p1"]["words"], by["p1"]["seconds"]) == (3, 3.0)
    assert (by["p2"]["words"], by["p2"]["seconds"]) == (1, 1.0)  # the muted word is out
    assert by["p1"]["share"] == pytest.approx(0.75)
    assert by["p2"]["share"] == pytest.approx(0.25)
    # Turns by speech_stats' rule: p1, p2, p1 -> 2 for p1, 1 for p2.
    assert (by["p1"]["turns"], by["p2"]["turns"]) == (2, 1)
    # Longest stretch: p1's first turn, "hello there", runs 0-2 s.
    assert by["p1"]["longest_seconds"] == 2.0
    assert talk["overlap_seconds"] == 0.5
    assert talk["words"] == 4
    assert [x["key"] for x in talk["speakers"]] == ["p1", "p2"]  # most talk first


def test_without_a_transcript_there_is_no_talk_section():
    for words in (None, []):
        assert "talk" not in project_stats.compute(build(), words=words)


def step(name, created, **args):
    return {"name": name, "args": args, "created": created}


def test_work_from_the_history_with_a_fake_clock():
    steps = [
        step("marker", "2026-10-19T09:00:00Z", kind="opened"),
        step("split_clip", "2026-10-19T10:00:00Z"),
        step("split_clips", "2026-10-19T10:05:00Z"),
        # 25 minutes away from the step before
        step("cut_range", "2026-10-19T10:30:00Z", start=sec(1), end=sec(4)),
        step("cut_words", "2026-10-19T10:34:00Z", indices=[1]),  # no range recorded
        step("clipboard_cut", "2026-10-19T10:34:30Z", start=sec(10), end=sec(12)),
        step("trim_clip", "2026-10-19T10:35:00Z"),
        step("marker", "2026-10-19T10:40:00Z", kind="closed"),
    ]
    cps = [{"kind": "manual", "created_utc": "2026-10-19T10:20:00Z"},
           {"kind": "export", "created_utc": "2026-10-19T10:34:00Z"}]
    now = datetime(2026, 10, 19, 12, 34, tzinfo=UTC)
    full = project_stats.compute(build(), steps=steps, checkpoints=cps, now=now)
    work = full["work"]
    assert work["steps"] == 6  # the opened/closed markers are not edits
    assert work["by_kind"]["split"] == 2
    assert work["by_kind"]["cut"] == 3
    assert work["by_kind"]["trim"] == 1
    assert work["first_edit"] == "2026-10-19T10:00:00Z"
    assert work["last_edit"] == "2026-10-19T10:35:00Z"
    # Gaps under 10 minutes: 5 + 4 + 0.5 + 0.5 min; the 25 minute one is not work.
    assert work["active_seconds"] == (5 + 4 + 0.5 + 0.5) * 60
    assert work["versions"] == 1
    assert work["exports"] == 1
    assert work["last_export"] == "2026-10-19T10:34:00Z"
    assert work["since_export_seconds"] == 2 * 3600
    assert full["runtime"]["cut_seconds"] == 5.0  # 3 s + 2 s
    assert full["runtime"]["cut_unmeasured"] == 1  # cut_words recorded no range


def test_no_undo_count_is_invented():
    # An undo moves the head and leaves no step behind: there is nothing to count.
    work = project_stats.compute(build())["work"]
    assert not [k for k in work if "undo" in k]


def test_empty_project_is_all_zeros():
    s = project_stats.compute(Project(rate=R), now=datetime(2026, 10, 19, tzinfo=UTC))
    assert s["runtime"] == {"edit_seconds": 0.0, "span_seconds": 0.0,
                            "recordings_seconds": 0.0, "cut_seconds": 0.0,
                            "cut_unmeasured": 0}
    assert s["counts"]["clips"] == 0
    assert s["counts"]["tracks"] == 0
    assert s["counts"]["clips_per_track"] == []
    assert s["work"]["steps"] == 0
    assert s["work"]["first_edit"] is None
    assert s["work"]["since_export_seconds"] is None
    assert "talk" not in s
    assert project_stats.to_text(s)  # the text builds without dividing by zero


def test_talk_with_no_speaking_time_has_zero_shares():
    s = project_stats.compute(build(), words=[w("x", 1, 2, "t1", muted=True)])
    assert "talk" not in s or all(x["share"] == 0 for x in s["talk"]["speakers"])


def test_text_is_translated():
    s = project_stats.compute(build(), words=WORDS)
    en = project_stats.to_text(s)
    assert "Runtime" in en
    messages.set_language("fi")
    fi = project_stats.to_text(s)
    assert fi != en
    assert "Kesto" in fi


# -- a real session: the numbers from the history file -------------------------


def session_with_history(tmp_path) -> Session:
    s = Session(tmp_path / "S.kuulas")
    p = build()
    for m in p.media:
        register(s.history, m.id, m.frames)
    s.history.commit("fixture", p)
    s.edit("split_clip", {"clip_id": "c2", "at": sec(15)})
    s.edit("cut_range", {"start": sec(1), "end": sec(3), "track_ids": ["t1"]})
    s.history.checkpoint("v1")
    return s


def clip_count(s: Session) -> int:
    return sum(len(t.clips) for t in s.history.state.tracks)


def test_session_stats_read_the_history(tmp_path):
    s = session_with_history(tmp_path)
    try:
        stats = s.stats()
        work = stats["work"]
        # The fixture commit has no op name; opening a new project writes no marker.
        assert work["steps"] == 2
        assert work["by_kind"] == {"split": 1, "cut": 1}
        assert work["versions"] == 1
        assert stats["runtime"]["cut_seconds"] == 2.0
        assert stats["counts"]["clips"] == clip_count(s)
        assert stats["size"]["project_bytes"] > 0
        # An undone step is not part of the current state's story.
        s.history.undo()
        assert s.stats()["work"]["steps"] == 1
        assert s.stats()["runtime"]["cut_seconds"] == 0.0
    finally:
        s.close()


def test_cut_words_records_its_range(tmp_path):
    s = Session(tmp_path / "W.kuulas")
    try:
        p = build()
        for m in p.media:
            register(s.history, m.id, m.frames)
        s.history.commit("fixture", p)
        words = [{"w": f"w{i}", "s": i * FLICKS, "e": int((i + 0.5) * FLICKS)}
                 for i in range(1, 8)]
        s.history.add_transcript("ma", words)
        s.command("cut_words", {"indices": [2]})
        node = s.history.nodes()[-1]
        assert node["op"]["name"] == "cut_words"
        assert node["op"]["args"]["end"] > node["op"]["args"]["start"]
        stats = s.stats()
        assert stats["runtime"]["cut_unmeasured"] == 0
        assert stats["runtime"]["cut_seconds"] > 0
        assert "talk" in stats
    finally:
        s.close()


class _Engine:
    def status(self):
        return {}

    def close(self):
        pass


def test_stats_endpoint(tmp_path):
    s = session_with_history(tmp_path)
    try:
        ui = tmp_path / "ui"
        ui.mkdir()
        with TestClient(create_app(s, _Engine(), language="en", ui_dir=ui)) as c:
            body = c.get("/api/stats").json()
            assert body["stats"]["counts"]["clips"] == clip_count(s)
            assert body["groups"][0]["title"] == "Runtime"
            assert all(len(row) == 2 for g in body["groups"] for row in g["rows"])
            assert "Runtime" in body["text"]
            assert c.get("/api/stats?format=text").text == body["text"]
    finally:
        s.close()


def test_cli_stats_prints_text_and_json(tmp_path, capsys):
    s = session_with_history(tmp_path)
    folder = str(s.package.path)
    s.close()
    assert cli.main(["stats", folder]) == 0
    out = capsys.readouterr().out
    assert "Runtime" in out
    assert "Clips" in out
    assert cli.main(["stats", folder, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["counts"]["tracks"] == 3
    assert cli.main(["stats", str(tmp_path / "nope")]) == 1


# -- speed ----------------------------------------------------------------------


def test_stats_on_the_heavy_hour_are_fast(tmp_path):
    s = Session(tmp_path / "Heavy.kuulas")
    try:
        project = heavy_hour()
        for m in project.media:
            register(s.history, m.id, m.frames)
        s.history.commit("heavy hour", project)
        for i in range(300):
            s.edit("set_track", {"track_id": "t0", "gain_db": -i * 0.01})
        words = [{"w": "x", "s": i * FLICKS, "e": int((i + 0.5) * FLICKS)}
                 for i in range(1, 3000)]
        for media in project.media:  # four hours of speech: ~12k words, 1,204 clips
            s.history.add_transcript(media.id, words)
        s.stats()  # warm up imports
        started = time.perf_counter()
        stats = s.stats()
        took = time.perf_counter() - started
        assert stats["counts"]["clips"] == 1204
        assert stats["talk"]["words"] > 0
        assert took < 0.5, f"{took * 1000:.0f} ms"
    finally:
        s.close()


def test_the_slow_work_runs_outside_the_session_lock(tmp_path, monkeypatch):
    s = session_with_history(tmp_path)
    try:
        held = []
        real = project_stats.compute

        def spy(*args, **kwargs):
            # The lock is re-entrant: only another thread can tell whether we hold it.
            got = []

            def try_lock():
                got.append(s.lock.acquire(timeout=1))
                if got[0]:
                    s.lock.release()

            thread = threading.Thread(target=try_lock)
            thread.start()
            thread.join()
            held.append(not got[0])
            return real(*args, **kwargs)

        monkeypatch.setattr(project_stats, "compute", spy)
        s.stats()
        assert held == [False]
    finally:
        s.close()
